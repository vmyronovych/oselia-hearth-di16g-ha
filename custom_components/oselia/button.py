"""Control buttons (Restart / Identify) -> <base>/<id>/cmd/<name> = PRESS.

Mirrors firmware/src/ha_discovery.py COMMAND_BUTTONS.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from . import OseliaConfigEntry
from .client import Gateway, OseliaClient
from .entity import OseliaEntity, setup_gateway_entities

# (key, name, command name, device_class)
BUTTONS = (
    ("reboot", "Restart", "reboot", ButtonDeviceClass.RESTART),
    ("identify", "Identify", "identify", ButtonDeviceClass.IDENTIFY),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OseliaConfigEntry,
    async_add_entities,
) -> None:
    setup_gateway_entities(
        hass,
        entry,
        async_add_entities,
        lambda client, gw: (OseliaButton(client, gw, *b) for b in BUTTONS),
    )


class OseliaButton(OseliaEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, client: OseliaClient, gateway: Gateway,
        key: str, name: str, command: str, device_class: ButtonDeviceClass,
    ) -> None:
        super().__init__(client, gateway)
        self._command = command
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_unique_id = f"hearth_{gateway.device_id}_{key}"

    async def async_press(self) -> None:
        self._client.publish_command(self._gw.device_id, self._command, "PRESS")
