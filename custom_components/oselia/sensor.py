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
from .entity import (
    OseliaEntity,
    setup_gateway_entities,
    setup_per_board_entities,
)


@dataclass(frozen=True, kw_only=True)
class OseliaSensorDescription(SensorEntityDescription):
    json_key: str = ""
    # If set, read from diag/state["counters"][counter_key] instead of a top-level key.
    counter_key: str = ""
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
        key="boards", json_key="boards", name="Input boards",
        icon="mdi:chip", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="boards_ok", json_key="boards_ok", name="Input boards responding",
        icon="mdi:chip", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="reset_cause", json_key="reset_cause", name="Last reset cause",
        icon="mdi:restart-alert", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Recovery/fault counters (fw >= 0.7.0; nested under diag/state.counters). Total-
    # increasing so HA keeps long-term statistics -- watch how often each recurs.
    OseliaSensorDescription(
        key="int_stuck", counter_key="int_stuck", name="INT stuck events",
        state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:alert-octagon",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="bus_recoveries", counter_key="bus_recoveries", name="I2C bus recoveries",
        state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:bus-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OseliaSensorDescription(
        key="mcp_resets", counter_key="mcp_resets", name="MCP resets",
        state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:restart",
        entity_category=EntityCategory.DIAGNOSTIC,
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
    def _gateway_sensors(client, gw):
        yield OseliaDiagnostics(client, gw)
        for d in SENSORS:
            yield OseliaSensor(client, gw, d)

    setup_gateway_entities(hass, entry, async_add_entities, _gateway_sensors)
    # Per-board "last error" sensors, added as the resolved board count grows.
    setup_per_board_entities(
        hass,
        entry,
        async_add_entities,
        lambda client, gw, board: [OseliaBoardError(client, gw, board)],
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
        desc = self.entity_description
        if desc.counter_key:
            counters = self._gw.diag.get("counters")
            value = counters.get(desc.counter_key) if isinstance(counters, dict) else None
        else:
            value = self._gw.diag.get(desc.json_key)
        if value is None:
            return None
        if desc.transform is not None:
            return desc.transform(value)
        return value


class OseliaDiagnostics(OseliaEntity, SensorEntity):
    """Single structured Diagnostics entity: state = the `health` summary, attributes
    = the entire diag/state blob. This is the canonical, copy-pasteable root-cause
    artifact -- export it from Developer Tools -> States, or via Download Diagnostics.
    """

    _attr_name = "Diagnostics"
    _attr_icon = "mdi:stethoscope"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, client: OseliaClient, gateway: Gateway) -> None:
        super().__init__(client, gateway)
        self._attr_unique_id = f"hearth_{gateway.device_id}_diagnostics"

    @property
    def native_value(self):
        # "ok" / "degraded" / "mcp_fault" / "net_fault"; "unknown" before first diag.
        return self._gw.diag.get("health", "unknown") if self._gw.diag else "unknown"

    @property
    def extra_state_attributes(self):
        return self._gw.diag or None


class OseliaBoardError(OseliaEntity, SensorEntity):
    """Per-board MCP last-error sensor: state = the error `code` ("ok" when healthy),
    with the raw detail + counters as attributes."""

    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, client: OseliaClient, gateway: Gateway, board: int) -> None:
        super().__init__(client, gateway)
        self._board = board
        self._attr_name = f"Board {board} MCP error"
        self._attr_unique_id = f"hearth_{gateway.device_id}_board{board}_mcp_error"

    @property
    def native_value(self):
        rec = self._gw.mcp_board(self._board)
        if not rec:
            return None
        if rec.get("ok"):
            return "ok"
        return rec.get("code") or "fault"

    @property
    def extra_state_attributes(self):
        rec = self._gw.mcp_board(self._board)
        if not rec:
            return None
        return {
            "addr": rec.get("addr"),
            "ok": rec.get("ok"),
            "detail": rec.get("detail"),
            "fails": rec.get("fails"),
            "last_ok_s": rec.get("last_ok_s"),
            "recoveries": rec.get("recoveries"),
        }
