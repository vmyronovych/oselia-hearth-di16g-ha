"""Firmware `update` entity -- the native HA OTA card for the gateway.

installed_version comes from diag/state `fw`; latest_version from the configured
release feed (CONF_RELEASE_URL). Install publishes the OTA command (see ota.py) and
progress is reflected from the retained <base>/<id>/ota/state.
"""
from __future__ import annotations

import logging

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant

from homeassistant.exceptions import HomeAssistantError

from . import OseliaConfigEntry
from .client import Gateway, OseliaClient
from .const import CONF_GITHUB_TOKEN, CONF_RELEASE_URL
from .entity import OseliaEntity, setup_gateway_entities
from .ota import (
    FeedError,
    OtaError,
    async_download_bundle,
    async_fetch_manifest,
    async_run_ota,
)

_LOGGER = logging.getLogger(__name__)

# OTA stages (from firmware OTA_SPEC.md ota/state.stage) that mean "in progress".
_IN_PROGRESS_STAGES = {"downloading", "applying"}

# Surfaced on the entity (and the dashboard's feed-error note) when no release feed is
# configured, so an installer sees *why* no update is offered instead of a misleading
# "Up to date". The actual fetch failures (private repo without a token, bad token, no
# published release, missing bundle asset) come from ota.py's FeedError messages.
_FEED_NOT_CONFIGURED = (
    "Firmware update feed not configured. Set the release URL (and, for the private "
    "repo, a GitHub token) in the OSELIA integration options."
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OseliaConfigEntry,
    async_add_entities,
) -> None:
    release_url = entry.options.get(CONF_RELEASE_URL) or entry.data.get(CONF_RELEASE_URL)
    token = entry.options.get(CONF_GITHUB_TOKEN) or entry.data.get(CONF_GITHUB_TOKEN)
    setup_gateway_entities(
        hass,
        entry,
        async_add_entities,
        lambda client, gw: [OseliaUpdate(client, gw, release_url, token)],
    )


class OseliaUpdate(OseliaEntity, UpdateEntity):
    _attr_name = "Firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES
    )
    # Poll the release feed periodically; gateway state changes still arrive via the
    # dispatcher (installed_version / progress) for instant UI updates.
    _attr_should_poll = True

    def __init__(
        self, client: OseliaClient, gateway: Gateway,
        release_url: str | None, token: str | None,
    ) -> None:
        super().__init__(client, gateway)
        self._release_url = release_url
        self._token = token
        self._manifest: dict | None = None
        self._feed_error: str | None = None
        self._attr_unique_id = f"hearth_{gateway.device_id}_firmware"

    @property
    def installed_version(self) -> str | None:
        return self._gw.sw_version

    @property
    def latest_version(self) -> str | None:
        if self._manifest:
            return self._manifest.get("version")
        return self.installed_version  # no feed -> no update offered

    @property
    def release_url(self) -> str | None:
        return (self._manifest or {}).get("release_url")

    @property
    def in_progress(self) -> bool:
        return (self._gw.ota.get("stage") or "idle") in _IN_PROGRESS_STAGES

    @property
    def update_percentage(self) -> float | None:
        if not self.in_progress:
            return None
        return self._gw.ota.get("percent")

    @property
    def extra_state_attributes(self) -> dict:
        # Surface release-feed problems straight on the entity so an installer sees
        # *why* no update is offered, without having to read the HA log. None only when
        # the feed last read cleanly; set (with a reason) when the feed is unconfigured
        # or errored -- the dashboard renders it as a warning note below the tile.
        return {"release_feed_error": self._feed_error}

    async def async_release_notes(self) -> str | None:
        return (self._manifest or {}).get("release_notes")

    async def async_update(self) -> None:
        if not self._release_url:
            # No feed to check -> say so (instead of silently looking "Up to date").
            self._feed_error = _FEED_NOT_CONFIGURED
            return
        try:
            self._manifest = await async_fetch_manifest(
                self.hass, self._release_url, self._token
            )
        except FeedError as err:
            # Keep the last good manifest (a transient blip shouldn't drop a found
            # update); record the reason and log once per distinct failure so the
            # log isn't spammed every poll.
            if self._feed_error != str(err):
                _LOGGER.warning(
                    "OSELIA firmware update check failed for %s: %s",
                    self._gw.device_id, err,
                )
            self._feed_error = str(err)
            return
        self._feed_error = None

    async def async_install(
        self, version: str | None, backup: bool, **kwargs
    ) -> None:
        if not self._manifest:
            raise HomeAssistantError("No firmware manifest (set the release URL).")
        if not self._client.connected:
            raise HomeAssistantError("Broker is offline; cannot reach the device.")
        try:
            bundle = await async_download_bundle(
                self.hass, self._manifest["url"], self._token
            )
            await async_run_ota(
                self.hass, self._client, self._gw,
                self._manifest["version"], bundle,
            )
        except OtaError as err:
            raise HomeAssistantError(f"OTA failed: {err}") from err
