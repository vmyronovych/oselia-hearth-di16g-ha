"""Diagnostics export for HA's one-click 'Download diagnostics'.

This is the primary export-to-Claude path: from the Hearth device page (or the
integration's config entry), 'Download diagnostics' produces a redacted JSON file
carrying the broker config (secrets removed), the integration's connection state, and
every gateway's live state -- including the structured diag/state blob (per-board MCP
health, error codes, recovery counters, reset_cause, and the recent[] fault timeline).
Hand that file to Claude to drive firmware fixes.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from . import OseliaConfigEntry
from .client import Gateway
from .const import CONF_GITHUB_TOKEN, CONF_PASSWORD, CONF_USERNAME, DOMAIN

# Never leak broker / feed credentials into an exported file.
TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, CONF_GITHUB_TOKEN}


def _gateway_dict(gw: Gateway) -> dict[str, Any]:
    """The live state of one gateway. The firmware diag/state blob is the rich part
    (health, per-board mcp[], counters, last_fault, recent[]); cfg/ota/log round it out.
    None of these carry secrets, so they are exported verbatim."""
    return {
        "device_id": gw.device_id,
        "available": gw.available,
        "sw_version": gw.sw_version,
        "ip": gw.ip,
        "boards": gw.boards,
        "boards_total": gw.boards_total,
        "diag": gw.diag,        # structured root-cause blob (the main artifact)
        "mcp": gw.mcp,          # per-board health (also inside diag, surfaced for ease)
        "cfg": gw.cfg,
        "ota": gw.ota,
        "log": gw.log,
    }


def _entry_block(entry: OseliaConfigEntry) -> dict[str, Any]:
    client = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "connected": client.connected,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OseliaConfigEntry
) -> dict[str, Any]:
    """Whole-integration export: every known gateway."""
    client = entry.runtime_data
    out = _entry_block(entry)
    out["gateways"] = {
        device_id: _gateway_dict(gw) for device_id, gw in client.gateways.items()
    }
    return out


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: OseliaConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Single-device export: the one Hearth gateway behind this device page."""
    client = entry.runtime_data
    out = _entry_block(entry)
    device_id = None
    for domain, ident in device.identifiers:
        if domain == DOMAIN and ident.startswith("hearth_"):
            device_id = ident[len("hearth_"):]
            break
    gw = client.gateways.get(device_id) if device_id else None
    out["gateway"] = _gateway_dict(gw) if gw else {"device_id": device_id, "note": "not currently on the broker"}
    return out
