"""OseliaClient -- the integration's own MQTT connection to the broker.

Deliberately does NOT use Home Assistant's `mqtt` integration: this integration owns
its connection so the gateway appears under OSELIA, not under the MQTT integration
(see INTEGRATION_SPEC.md, decision "own MQTT connection").

paho-mqtt runs its network loop on a background thread; all callbacks are marshalled
onto the HA event loop via `loop.call_soon_threadsafe` before any dispatcher_send.
Written to work with both paho-mqtt 1.x and 2.x callback APIs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    PINS_PER_CHIP,
    SIGNAL_ACTION,
    SIGNAL_CONNECTION,
    SIGNAL_FAULT,
    SIGNAL_GATEWAY_UPDATE,
    SIGNAL_NEW_BOARDS,
    SIGNAL_NEW_GATEWAY,
    SIGNAL_NEW_INPUTS,
    SIGNAL_OTA_NAK,
)

_LOGGER = logging.getLogger(__name__)

# A gateway's device_id is the firmware's _device_id(): the last 6 hex of the MCU id,
# or a DEVICE_ID override (a short, plain token). Anything else arriving in the topic's
# id slot is not a real gateway -- e.g. a stray publish whose id was polluted with
# boot-serial text -- and must be rejected so it can't spawn a phantom device/entities.
_VALID_DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class Gateway:
    """Live state for one Hearth gateway, keyed by device_id."""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self.available = False
        self.diag: dict = {}
        self.cfg: dict = {}
        self.ota: dict = {}
        self.log: dict = {}
        self.boards = 0  # number of input boards known (boards * 16 = inputs)
        self.boards_total = 0  # resolved board count (drives per-board MCP entities)
        self.mcp: list = []  # per-board MCP health from diag/state.mcp (fw >= 0.7.0)

    @property
    def sw_version(self) -> str | None:
        return self.diag.get("fw")

    def mcp_board(self, board: int) -> dict:
        """Per-board MCP health record (1-based) from diag/state.mcp, or {}."""
        idx = board - 1
        if 0 <= idx < len(self.mcp):
            rec = self.mcp[idx]
            if isinstance(rec, dict):
                return rec
        return {}

    @property
    def ip(self) -> str | None:
        return self.diag.get("ip")

    @property
    def name(self) -> str:
        # device_id is the last hex of the MCU id; a stable, human-ish suffix.
        return f"Hearth {self.device_id}"


class OseliaClient:
    """Owns the broker connection and fans messages out to entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        base_topic: str,
    ) -> None:
        self.hass = hass
        self._host = host
        self._port = port
        self._base = base_topic
        self.gateways: dict[str, Gateway] = {}
        self.connected = False               # broker-link state (drives availability)

        if hasattr(mqtt, "CallbackAPIVersion"):  # paho-mqtt 2.x
            self._mqtt = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2
            )
        else:  # paho-mqtt 1.x
            self._mqtt = mqtt.Client()
        if username:
            self._mqtt.username_pw_set(username, password or "")
        # Snappier recovery than paho's default 1->120s backoff: retry the broker every
        # 1..30s. loop_start() auto-reconnects; _on_connect re-subscribes each time.
        self._mqtt.reconnect_delay_set(min_delay=1, max_delay=30)
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_disconnect = self._on_disconnect
        self._mqtt.on_message = self._on_message

    # ---- lifecycle -------------------------------------------------------
    async def async_start(self) -> None:
        # connect_async never blocks and never raises on an unreachable broker: the
        # loop thread does the connect and retries with backoff. So a broker that is
        # down at startup never fails entry setup -- the integration loads and keeps
        # trying in the background, reporting "disconnected" until it succeeds.
        try:
            self._mqtt.connect_async(self._host, self._port, keepalive=60)
        except (OSError, ValueError) as err:  # pragma: no cover - defensive
            _LOGGER.error("OSELIA connect setup error (will keep retrying): %s", err)
        self._mqtt.loop_start()  # background network thread (connects + auto-retries)

    async def async_stop(self) -> None:
        self._mqtt.loop_stop()
        await self.hass.async_add_executor_job(self._mqtt.disconnect)

    # ---- paho callbacks (network thread) ---------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, *args) -> None:
        b = self._base
        # One subscription per topic family; '+' wildcards over device_id / board / pin.
        for topic in (
            f"{b}/+/status",
            f"{b}/+/diag/state",
            f"{b}/+/diag/log",
            f"{b}/+/diag/event",
            f"{b}/+/cfg",
            f"{b}/+/ota/state",
            f"{b}/+/ota/nak",
            f"{b}/+/+/+/action",  # <base>/<id>/board<b>/input<p>/action
        ):
            client.subscribe(topic, qos=0)
        _LOGGER.info("OSELIA MQTT connected to %s:%s", self._host, self._port)
        self.hass.loop.call_soon_threadsafe(self._set_connected, True)

    def _on_disconnect(self, client, userdata, *args) -> None:
        # paho 1.x: (client, userdata, rc); 2.x: (client, userdata, flags,
        # reason_code, properties). Absorb the difference with *args.
        _LOGGER.warning("OSELIA MQTT disconnected from broker; auto-reconnecting")
        self.hass.loop.call_soon_threadsafe(self._set_connected, False)

    @callback
    def _set_connected(self, state: bool) -> None:
        """Update broker-link state and refresh every entity's availability."""
        if state == self.connected:
            return
        self.connected = state
        async_dispatcher_send(self.hass, SIGNAL_CONNECTION)   # broker-status entity
        for device_id in self.gateways:
            async_dispatcher_send(self.hass, SIGNAL_GATEWAY_UPDATE.format(device_id))

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = msg.payload.decode("utf-8", "replace")
        except Exception:  # pragma: no cover - defensive
            return
        # Hop to the HA event loop as a *task* (run_coroutine_threadsafe), not a bare
        # callback: async_add_entities eager-starts a task and calls
        # asyncio.current_task(), which needs a running task context -- a plain
        # call_soon_threadsafe callback has none and trips "no running event loop".
        asyncio.run_coroutine_threadsafe(
            self._async_handle(msg.topic, payload, msg.retain), self.hass.loop
        )

    # ---- message handling (event loop task) ------------------------------
    async def _async_handle(
        self, topic: str, payload: str, retain: bool = False
    ) -> None:
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != self._base:
            return
        device_id = parts[1]
        if not _VALID_DEVICE_ID.match(device_id):
            # Not a plausible gateway id (e.g. a stray publish to <base>/<garbage>/...);
            # drop it rather than create a phantom gateway, device, and entities.
            _LOGGER.warning("OSELIA ignoring message with implausible device id %r",
                            device_id)
            return
        gw, is_new = self._ensure_gateway(device_id)

        rest = parts[2:]
        if rest == ["status"]:
            gw.available = payload.strip() == "online"
        elif rest == ["diag", "state"]:
            self._apply_diag(gw, payload)
        elif rest == ["diag", "log"]:
            gw.log = _safe_json(payload)
        elif rest == ["diag", "event"]:
            # A fault is a momentary event (non-retained). A retained copy on
            # (re)subscribe would be a stale replay -- drop it, like actions.
            if retain:
                return
            fault = _safe_json(payload)
            if fault:
                async_dispatcher_send(
                    self.hass, SIGNAL_FAULT.format(device_id), fault
                )
            return  # events are not state -- no general update signal
        elif rest == ["cfg"]:
            gw.cfg = _safe_json(payload)
        elif rest == ["ota", "state"]:
            gw.ota = _safe_json(payload)
        elif rest == ["ota", "nak"]:
            try:
                missing = json.loads(payload)
            except (ValueError, TypeError):
                return
            async_dispatcher_send(
                self.hass, SIGNAL_OTA_NAK.format(device_id), missing
            )
            return  # NAK feeds the active install only -- no general update signal
        elif len(rest) == 3 and rest[0].startswith("board") and rest[2] == "action":
            # A gesture is a momentary event, never state. A RETAINED action is a stale
            # copy the broker replays to us the instant we (re)subscribe -- e.g. after a
            # gateway Restart churns the connection. Acting on it would re-fire the event
            # entity / device-trigger and run the user's blueprint automations, flipping
            # relays out of nowhere. Drop retained actions; only live gestures count.
            if retain:
                _LOGGER.debug(
                    "OSELIA ignoring retained action on %s (stale gesture replay)", topic
                )
                return
            self._handle_action(gw, rest, payload)
            return  # actions are events, not state -- no general update signal
        else:
            return

        if is_new:
            async_dispatcher_send(self.hass, SIGNAL_NEW_GATEWAY, device_id)
        async_dispatcher_send(self.hass, SIGNAL_GATEWAY_UPDATE.format(device_id))

    def _ensure_gateway(self, device_id: str) -> tuple[Gateway, bool]:
        gw = self.gateways.get(device_id)
        if gw is None:
            gw = self.gateways[device_id] = Gateway(device_id)
            return gw, True
        return gw, False

    def _apply_diag(self, gw: Gateway, payload: str) -> None:
        gw.diag = _safe_json(payload)
        gw.mcp = gw.diag.get("mcp") if isinstance(gw.diag.get("mcp"), list) else []
        boards = gw.diag.get("boards") or 0
        # `boards` can read 0 transiently if the MCPs aren't answering; only grow the
        # known input set, never shrink it, so entities don't churn.
        if boards > gw.boards:
            gw.boards = boards
            async_dispatcher_send(
                self.hass, SIGNAL_NEW_INPUTS.format(gw.device_id), boards
            )
        # Resolved board count (fw >= 0.7.0; falls back to `boards`) drives the
        # per-board MCP health entities -- grow-only, same as inputs.
        boards_total = gw.diag.get("boards_total") or boards
        if boards_total > gw.boards_total:
            gw.boards_total = boards_total
            async_dispatcher_send(
                self.hass, SIGNAL_NEW_BOARDS.format(gw.device_id), boards_total
            )

    def _handle_action(self, gw: Gateway, rest: list[str], payload: str) -> None:
        try:
            board = int(rest[0].removeprefix("board"))
            pin = int(rest[1].removeprefix("input"))
        except ValueError:
            return
        async_dispatcher_send(
            self.hass, SIGNAL_ACTION.format(gw.device_id), board, pin, payload.strip()
        )

    # ---- publishing (HA -> device) ---------------------------------------
    def publish_command(self, device_id: str, name: str, payload: str) -> None:
        """HA -> device command on <base>/<id>/cmd/<name>."""
        self._mqtt.publish(f"{self._base}/{device_id}/cmd/{name}", payload, qos=0)

    def publish_ota(self, device_id: str, command: dict) -> None:
        """Trigger OTA on <base>/<id>/ota/cmd (see INTEGRATION_SPEC.md 'OTA')."""
        self._mqtt.publish(
            f"{self._base}/{device_id}/ota/cmd", json.dumps(command), qos=1
        )

    def publish_ota_chunk(self, device_id: str, payload: bytes) -> None:
        """MQTT-chunked OTA transport: ordered bundle chunks on <base>/<id>/ota/data."""
        self._mqtt.publish(f"{self._base}/{device_id}/ota/data", payload, qos=1)

    # ---- helpers for entities --------------------------------------------
    @staticmethod
    def input_count(boards: int) -> int:
        return boards * PINS_PER_CHIP


def _safe_json(payload: str) -> dict:
    try:
        data = json.loads(payload)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}
