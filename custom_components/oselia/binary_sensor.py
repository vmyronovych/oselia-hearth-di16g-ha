"""Binary sensors:
- per-gateway Ethernet-link (from diag/state `eth`, mirrors firmware diag.py), and
- an always-present "Broker connection" sensor on a hub device that reports the
  integration's own MQTT link -- visible on the integration/device page and the
  dashboard even when no gateway has been seen (e.g. broker down at startup).
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import OseliaConfigEntry
from .client import Gateway, OseliaClient
from .const import DOMAIN, MANUFACTURER, SIGNAL_CONNECTION
from .entity import OseliaEntity, setup_gateway_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OseliaConfigEntry,
    async_add_entities,
) -> None:
    # The broker-connection sensor is added unconditionally at setup (not via gateway
    # discovery), so the status is shown even if the broker never connects.
    async_add_entities([OseliaBrokerConnection(entry.runtime_data, entry)])
    setup_gateway_entities(
        hass,
        entry,
        async_add_entities,
        lambda client, gw: [OseliaEthernet(client, gw)],
    )


class OseliaEthernet(OseliaEntity, BinarySensorEntity):
    _attr_name = "Ethernet link"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, client: OseliaClient, gateway: Gateway) -> None:
        super().__init__(client, gateway)
        self._attr_unique_id = f"hearth_{gateway.device_id}_diag_ethernet"

    @property
    def is_on(self) -> bool | None:
        return self._gw.diag.get("eth")


class OseliaBrokerConnection(BinarySensorEntity):
    """Integration-level MQTT broker link, on a service 'hub' device.

    Always available (so it can report 'disconnected'); reflects client.connected and
    refreshes on the broker connect/disconnect signal.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Broker connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, client: OseliaClient, entry: OseliaConfigEntry) -> None:
        self._client = client
        self._attr_unique_id = f"oselia_broker_{entry.entry_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"hub_{entry.entry_id}")},
            name="OSELIA",
            manufacturer=MANUFACTURER,
            model="MQTT bridge",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        return True  # always available, so it can report up OR down

    @property
    def is_on(self) -> bool:
        return self._client.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CONNECTION, self._update)
        )

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()
