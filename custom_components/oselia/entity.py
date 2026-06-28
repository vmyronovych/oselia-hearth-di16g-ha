"""Shared base for OSELIA entities: device_info + availability + update wiring."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import Gateway, OseliaClient
from .const import (
    DEFAULT_MODEL,
    DOMAIN,
    MANUFACTURER,
    SIGNAL_GATEWAY_UPDATE,
    SIGNAL_NEW_BOARDS,
    SIGNAL_NEW_GATEWAY,
)


@callback
def setup_gateway_entities(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[OseliaClient, Gateway], Iterable[Entity]],
) -> None:
    """Add the static per-gateway entities for existing and future gateways.

    `factory(client, gateway)` returns this platform's entities for one gateway; it is
    called once per gateway (those already discovered at setup, then each new one).
    """
    client: OseliaClient = entry.runtime_data

    @callback  # MUST be @callback: dispatcher runs non-callback targets in an executor
    def _add(device_id: str) -> None:  # thread (no loop) -> async_add_entities breaks.
        async_add_entities(list(factory(client, client.gateways[device_id])))

    for device_id in list(client.gateways):
        _add(device_id)
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_GATEWAY, _add)
    )


@callback
def setup_per_board_entities(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[OseliaClient, Gateway, int], Iterable[Entity]],
) -> None:
    """Add per-board entities as the gateway's board count becomes known/grows.

    `factory(client, gateway, board)` returns this platform's entities for one board
    (1-based). Called once per (gateway, board); never removed if the count dips, so
    a transiently-down board doesn't churn the registry. Mirrors the per-input
    pattern in event.py but keyed on SIGNAL_NEW_BOARDS (= boards_total).
    """
    client: OseliaClient = entry.runtime_data
    created: set[tuple[str, int]] = set()

    @callback
    def _add(device_id: str, boards_total: int) -> None:
        gw = client.gateways[device_id]
        new: list[Entity] = []
        for board in range(1, boards_total + 1):
            key = (device_id, board)
            if key in created:
                continue
            created.add(key)
            new.extend(factory(client, gw, board))
        if new:
            async_add_entities(new)

    @callback
    def _on_new_gateway(device_id: str) -> None:
        gw = client.gateways[device_id]
        if gw.boards_total:
            _add(device_id, gw.boards_total)

        @callback
        def _boards_changed(boards_total: int) -> None:
            _add(device_id, boards_total)

        entry.async_on_unload(
            async_dispatcher_connect(
                hass, SIGNAL_NEW_BOARDS.format(device_id), _boards_changed
            )
        )

    for device_id in list(client.gateways):
        _on_new_gateway(device_id)
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_GATEWAY, _on_new_gateway)
    )


class OseliaEntity(Entity):
    """Base entity tied to one gateway; refreshes on the per-gateway update signal."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client: OseliaClient, gateway: Gateway) -> None:
        self._client = client
        self._gw = gateway

    @property
    def device_info(self):
        gw = self._gw
        url = f"http://{gw.ip}" if gw.ip and gw.ip not in ("dhcp", "") else None
        return {
            "identifiers": {(DOMAIN, f"hearth_{gw.device_id}")},
            "name": gw.name,
            "manufacturer": MANUFACTURER,
            "model": gw.diag.get("model", DEFAULT_MODEL),
            "sw_version": gw.sw_version,
            "serial_number": gw.device_id,
            "configuration_url": url,
        }

    @property
    def available(self) -> bool:
        # Unavailable if our broker link is down (we can't know the device's state) OR
        # the device's own LWT says it's offline.
        return self._client.connected and self._gw.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_GATEWAY_UPDATE.format(self._gw.device_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
