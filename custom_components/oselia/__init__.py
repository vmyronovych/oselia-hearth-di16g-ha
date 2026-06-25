"""OSELIA Hearth integration -- setup/teardown.

Owns an MQTT connection per config entry (one per broker) and forwards to the entity
platforms. See INTEGRATION_SPEC.md.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .client import OseliaClient
from .const import (
    CONF_BASE_TOPIC,
    CONF_BROKER,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    DEFAULT_BASE_TOPIC,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
)

type OseliaConfigEntry = ConfigEntry[OseliaClient]


async def async_setup_entry(hass: HomeAssistant, entry: OseliaConfigEntry) -> bool:
    """Connect to the broker and set up the platforms."""
    data = entry.data
    client = OseliaClient(
        hass,
        host=data[CONF_BROKER],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        username=data.get(CONF_USERNAME),
        password=data.get(CONF_PASSWORD),
        base_topic=data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC),
    )
    await client.async_start()
    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: OseliaConfigEntry) -> None:
    """Reload on options change (e.g. the release-feed URL)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: OseliaConfigEntry) -> bool:
    """Tear down the platforms and disconnect the broker."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: OseliaConfigEntry, device: DeviceEntry
) -> bool:
    """Allow deleting a gateway device that is no longer present on the broker.

    A gateway only re-appears if it publishes its retained topics, so a device that
    the live client doesn't currently know (offline + retained cleared, or a stale
    test unit) is safe to remove from the registry.
    """
    client = entry.runtime_data
    for domain, ident in device.identifiers:
        if domain == DOMAIN and ident.startswith("hearth_"):
            return ident[len("hearth_") :] not in client.gateways
    return True
