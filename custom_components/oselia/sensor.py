"""Diagnostic sensors from the gateway's retained diag/state.

Mirrors firmware/src/diag.py DIAG_SENSORS (minus the Ethernet binary_sensor, which is
in binary_sensor.py). The firmware diag/state JSON is the contract.
"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant

from . import OseliaConfigEntry
from .client import Gateway, OseliaClient
from .entity import OseliaEntity, setup_gateway_entities


@dataclass(frozen=True, kw_only=True)
class OseliaSensorDescription(SensorEntityDescription):
    json_key: str = ""
    # Optional transform applied to the raw JSON value before display.
    transform: callable | None = None


SENSORS: tuple[OseliaSensorDescription, ...] = (
    OseliaSensorDescription(
        key="uptime", json_key="uptime_s", name="Uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,   # whole seconds, not "86,400.00 s"
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="mem_free", json_key="mem_free", name="Free memory",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    OseliaSensorDescription(
        key="temperature", json_key="temp_c", name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="reconnects", json_key="reconnects", name="Reconnects",
        state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:restart",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="dropped", json_key="dropped", name="Dropped events",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:trash-can-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="boards", json_key="boards", name="Input boards online",
        icon="mdi:chip", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="board_addrs", json_key="board_addrs", name="Board addresses",
        icon="mdi:identifier", entity_category=EntityCategory.DIAGNOSTIC,
        transform=lambda v: ", ".join(v) if isinstance(v, list) else v,
    ),
    OseliaSensorDescription(
        key="last_input", json_key="last", name="Last input",
        icon="mdi:gesture-tap-button", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="ip", json_key="ip", name="IP address",
        icon="mdi:ip-network", entity_category=EntityCategory.DIAGNOSTIC,
    ),
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
        lambda client, gw: (OseliaSensor(client, gw, d) for d in SENSORS),
    )


class OseliaSensor(OseliaEntity, SensorEntity):
    entity_description: OseliaSensorDescription

    def __init__(
        self, client: OseliaClient, gateway: Gateway,
        description: OseliaSensorDescription,
    ) -> None:
        super().__init__(client, gateway)
        self.entity_description = description
        self._attr_unique_id = f"hearth_{gateway.device_id}_diag_{description.key}"

    @property
    def native_value(self):
        value = self._gw.diag.get(self.entity_description.json_key)
        if value is None:
            return None
        if self.entity_description.transform is not None:
            return self.entity_description.transform(value)
        return value
