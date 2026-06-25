"""Live-tunable gesture timings (number entities) -> <base>/<id>/cmd/<key> = <ms>.

State reflects the retained <base>/<id>/cfg JSON. Mirrors firmware
ha_discovery.TUNABLE_NUMBERS; the firmware clamps inbound values to the same limits.
"""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant

from . import OseliaConfigEntry
from .client import Gateway, OseliaClient
from .entity import OseliaEntity, setup_gateway_entities

# (key, name, min, max, step)
NUMBERS = (
    ("long_ms", "Long press time", 100, 2000, 50),
    ("double_gap_ms", "Double-tap window", 0, 1000, 50),
    ("debounce_ms", "Debounce time", 0, 100, 5),
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
        lambda client, gw: (OseliaNumber(client, gw, *n) for n in NUMBERS),
    )


class OseliaNumber(OseliaEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
    _attr_mode = NumberMode.BOX

    def __init__(
        self, client: OseliaClient, gateway: Gateway,
        key: str, name: str, lo: int, hi: int, step: int,
    ) -> None:
        super().__init__(client, gateway)
        self._key = key
        self._attr_name = name
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_native_step = step
        self._attr_unique_id = f"hearth_{gateway.device_id}_{key}"

    @property
    def native_value(self) -> float | None:
        return self._gw.cfg.get(self._key)

    async def async_set_native_value(self, value: float) -> None:
        self._client.publish_command(self._gw.device_id, self._key, str(int(value)))
