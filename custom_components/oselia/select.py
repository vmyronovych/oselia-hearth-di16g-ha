"""Log-level select -> <base>/<id>/cmd/log_level = <LEVEL>.

The retained cfg JSON stores log_level as an integer index into LOG_LEVELS (matching
firmware ha_discovery.LOG_LEVEL_OPTIONS and its value_template); the command publishes
the level name, which the firmware parses.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from . import OseliaConfigEntry
from .client import Gateway, OseliaClient
from .entity import OseliaEntity, setup_gateway_entities

LOG_LEVELS = ["ERROR", "WARN", "INFO", "DEBUG"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OseliaConfigEntry,
    async_add_entities,
) -> None:
    setup_gateway_entities(
        hass,
        entry,
        async_add_entities,
        lambda client, gw: [OseliaLogLevel(client, gw)],
    )


class OseliaLogLevel(OseliaEntity, SelectEntity):
    _attr_name = "Log level"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bug-outline"
    _attr_options = LOG_LEVELS

    def __init__(self, client: OseliaClient, gateway: Gateway) -> None:
        super().__init__(client, gateway)
        self._attr_unique_id = f"hearth_{gateway.device_id}_log_level"

    @property
    def current_option(self) -> str | None:
        idx = self._gw.cfg.get("log_level")
        if isinstance(idx, int) and 0 <= idx < len(LOG_LEVELS):
            return LOG_LEVELS[idx]
        if isinstance(idx, str) and idx in LOG_LEVELS:  # tolerate a name too
            return idx
        return None

    async def async_select_option(self, option: str) -> None:
        self._client.publish_command(self._gw.device_id, "log_level", option)
