"""Device-automation triggers for input gestures (single/double/long press).

HA's `event` domain does not generate device triggers, so the integration provides
them here -- restoring the "<input> button short/double/long press" entries the old
MQTT-discovery firmware published as `device_automation` configs. We reuse the
standard HA trigger types (button_short_press/double_press/long_press) so HA renders
and localizes them for free.

Inputs are enumerated from the device's `event` entities in the registry (so the
picker works even while the gateway is offline). A trigger fires off the same internal
SIGNAL_ACTION dispatcher the event entities consume.
"""
from __future__ import annotations

import re

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SIGNAL_ACTION

CONF_SUBTYPE = "subtype"

# gesture (firmware action payload) <-> standard HA device-trigger type
GESTURE_TO_TYPE = {
    "single": "button_short_press",
    "double": "button_double_press",
    "long": "button_long_press",
}
TYPE_TO_GESTURE = {v: k for k, v in GESTURE_TO_TYPE.items()}

_SUBTYPE_RE = re.compile(r"^board(\d+)_input(\d+)$")
_UNIQUE_RE = re.compile(r"_b(\d+)_in(\d+)_event$")

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TYPE_TO_GESTURE),
        vol.Required(CONF_SUBTYPE): str,
    }
)


def _gateway_id(hass: HomeAssistant, ha_device_id: str) -> str | None:
    """Map an HA device id -> the gateway's firmware device_id via its identifiers."""
    device = dr.async_get(hass).async_get(ha_device_id)
    if not device:
        return None
    for domain, ident in device.identifiers:
        if domain == DOMAIN and ident.startswith("hearth_"):
            return ident[len("hearth_") :]
    return None


def _inputs_for_device(hass: HomeAssistant, ha_device_id: str) -> list[tuple[int, int]]:
    """(board, pin) pairs from the device's `event` entities in the registry."""
    ent_reg = er.async_get(hass)
    inputs: list[tuple[int, int]] = []
    for entry in er.async_entries_for_device(
        ent_reg, ha_device_id, include_disabled_entities=True
    ):
        if entry.domain == "event" and entry.platform == DOMAIN:
            m = _UNIQUE_RE.search(entry.unique_id)
            if m:
                inputs.append((int(m.group(1)), int(m.group(2))))
    return sorted(inputs)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """One trigger per (input x gesture)."""
    triggers: list[dict[str, str]] = []
    for board, pin in _inputs_for_device(hass, device_id):
        subtype = "board%d_input%d" % (board, pin)
        for trig_type in TYPE_TO_GESTURE:
            triggers.append(
                {
                    CONF_PLATFORM: "device",
                    CONF_DOMAIN: DOMAIN,
                    CONF_DEVICE_ID: device_id,
                    CONF_TYPE: trig_type,
                    CONF_SUBTYPE: subtype,
                }
            )
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Fire the action when the matching input gesture arrives on SIGNAL_ACTION."""
    gw_id = _gateway_id(hass, config[CONF_DEVICE_ID])
    gesture = TYPE_TO_GESTURE[config[CONF_TYPE]]
    m = _SUBTYPE_RE.match(config[CONF_SUBTYPE])
    board, pin = (int(m.group(1)), int(m.group(2))) if m else (None, None)

    job = HassJob(action, f"oselia trigger {config[CONF_SUBTYPE]} {config[CONF_TYPE]}")
    trigger_data = trigger_info["trigger_data"]

    @callback
    def _on_action(b: int, p: int, g: str) -> None:
        if b != board or p != pin or g != gesture:
            return
        hass.async_run_hass_job(
            job,
            {
                "trigger": {
                    **trigger_data,
                    "platform": "device",
                    "domain": DOMAIN,
                    "device_id": config[CONF_DEVICE_ID],
                    "type": config[CONF_TYPE],
                    "subtype": config[CONF_SUBTYPE],
                    "description": "OSELIA %s %s"
                    % (config[CONF_SUBTYPE], config[CONF_TYPE]),
                }
            },
        )

    if gw_id is None or board is None:
        return lambda: None
    return async_dispatcher_connect(hass, SIGNAL_ACTION.format(gw_id), _on_action)
