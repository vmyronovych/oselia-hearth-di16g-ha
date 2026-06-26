"""OTA driver: fetch the release manifest + bundle and stream it to a gateway.

Transport = MQTT-chunked over the integration's own broker connection (no CH9120
retarget), matching firmware/OTA_SPEC.md and the reference publisher
firmware/tools/ota_publish.py. The on-device receiver is implemented and HW-verified.

A release manifest is a small JSON document (GitHub Releases asset or any URL):

    {"version": "0.2.0", "url": "https://.../hearth-0.2.0.bundle",
     "release_notes": "...", "release_url": "https://..."}

`url` points at a bundle artifact built by firmware/tools/ota_build.py (a manifest
line + concatenated file bytes); the device verifies its sha256 before applying.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import struct
import time

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .client import Gateway, OseliaClient
from .const import (
    OTA_CHUNK_DELAY,
    OTA_CHUNK_SIZE,
    OTA_CMD_RETRIES,
    OTA_INSTALL_TIMEOUT,
    SIGNAL_OTA_NAK,
)

_LOGGER = logging.getLogger(__name__)


class OtaError(Exception):
    """An OTA install failed (reported back to the UpdateEntity)."""


class FeedError(Exception):
    """The release feed could not be read or understood.

    Carries an installer-friendly message: the UpdateEntity surfaces it as a state
    attribute and the options flow shows it inline, so a misconfigured feed (private
    repo without a token, bad token, no published release, missing bundle asset)
    gives instant feedback instead of silently showing "Up to date".
    """


def _http_error_message(err: aiohttp.ClientResponseError) -> str:
    """Map a GitHub/HTTP status to an actionable explanation."""
    if err.status == 404:
        return (
            "Release feed not found (HTTP 404). For a PRIVATE repo this means no "
            "GitHub token is set, or the token can't see the repo. For a public repo "
            "it means there is no published (non-draft, non-prerelease) release yet."
        )
    if err.status in (401, 403):
        return (
            f"Release feed access denied (HTTP {err.status}). The GitHub token is "
            "missing, expired, or lacks read-only 'Contents' access to the repo."
        )
    return f"Release feed returned HTTP {err.status}: {err.message}."


def _auth_headers(token: str | None, accept: str | None = None) -> dict:
    h: dict = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
        h["X-GitHub-Api-Version"] = "2022-11-28"
    if accept:
        h["Accept"] = accept
    return h


async def _fetch_bytes(
    hass: HomeAssistant, url: str, token: str | None, accept: str, timeout: int
) -> bytes:
    """GET `url` and return the body, mapping any failure to FeedError.

    Authenticates with `token` when one is given. If an *authenticated* request is
    rejected with 401/403 -- e.g. a leftover or over-scoped token pointed at a now
    PUBLIC repo -- it retries once WITHOUT the token, so a public feed keeps working
    even when a stale token lingers in the options. The auth error is surfaced only if
    the unauthenticated retry ALSO fails, so a genuinely PRIVATE repo still gets a clear
    token message instead of a misleading "up to date".
    """
    session = async_get_clientsession(hass)
    attempts = [token, None] if token else [None]
    auth_err: aiohttp.ClientResponseError | None = None
    for i, attempt_token in enumerate(attempts):
        try:
            async with session.get(
                url, headers=_auth_headers(attempt_token, accept), timeout=timeout
            ) as resp:
                resp.raise_for_status()
                return await resp.read()
        except aiohttp.ClientResponseError as err:
            # A denied token request, with a tokenless retry still to come -> retry.
            if err.status in (401, 403) and attempt_token is not None and i + 1 < len(attempts):
                auth_err = err
                _LOGGER.debug(
                    "OSELIA feed: token rejected (HTTP %s) for %s; retrying unauthenticated",
                    err.status, url,
                )
                continue
            raise FeedError(_http_error_message(err)) from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise FeedError(f"Could not reach the release feed {url}: {err}") from err
    # The loop always returns or raises above; this is just for completeness.
    raise FeedError(_http_error_message(auth_err))  # pragma: no cover


async def async_fetch_manifest(
    hass: HomeAssistant, url: str, token: str | None = None
) -> dict:
    """Fetch + normalize the latest-firmware manifest.

    Accepts either a plain manifest JSON (`{version, url, ...}`) OR a GitHub Releases
    API object (`https://api.github.com/repos/<o>/<r>/releases/latest`). For the API
    form we read the `manifest.json` asset for metadata and use the `.bundle` asset's
    API URL for the download; these work without a token on a PUBLIC repo and with a
    `token` on a PRIVATE one (a stale token on a public repo is handled -- see
    `_fetch_bytes`).

    Raises FeedError (with an installer-facing message) on any failure -- the caller
    surfaces it instead of silently treating "no update found" the same as "up to date".
    """
    raw = await _fetch_bytes(hass, url, token, "application/vnd.github+json", 15)
    import json as _json
    try:
        data = _json.loads(raw)
    except ValueError as err:
        raise FeedError(f"Release feed {url} did not return valid JSON.") from err
    if isinstance(data, dict) and "tag_name" in data and "assets" in data:
        return await _manifest_from_release(hass, data, token)
    if isinstance(data, dict) and "version" in data and "url" in data:
        return data
    raise FeedError(
        f"Release feed {url} is neither a manifest JSON nor a GitHub release object."
    )


async def _manifest_from_release(hass, release: dict, token: str | None) -> dict:
    """Turn a GitHub release object into our manifest dict (raises FeedError if unusable)."""
    assets = release.get("assets") or []
    bundle = next(
        (a for a in assets if str(a.get("name", "")).endswith(".bundle")), None
    )
    if not bundle:
        raise FeedError(
            f"GitHub release {release.get('tag_name')!r} has no '.bundle' asset; "
            "the firmware bundle was not uploaded to the release."
        )
    out = {
        "url": bundle["url"],                       # asset API URL (honors the token)
        "release_url": release.get("html_url"),
        "release_notes": release.get("body") or "",
    }
    man = next((a for a in assets if a.get("name") == "manifest.json"), None)
    if man:
        meta = await _download_json_asset(hass, man["url"], token)
        if isinstance(meta, dict):
            out["version"] = meta.get("version")
            out["sha256"] = meta.get("sha256")
    if not out.get("version"):                      # fallback: derive from the tag
        tag = release.get("tag_name", "")
        out["version"] = tag[4:] if tag.startswith("fw-v") else tag.lstrip("v")
    return out


async def _download_json_asset(hass, url: str, token: str | None) -> dict | None:
    try:
        raw = await _fetch_bytes(hass, url, token, "application/octet-stream", 15)
        import json as _json
        return _json.loads(raw)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("OSELIA manifest asset fetch failed: %s", err)
        return None


async def async_download_bundle(
    hass: HomeAssistant, url: str, token: str | None = None
) -> bytes:
    """Download the firmware bundle. A GitHub asset API URL works without a token on a
    PUBLIC repo and with the token on a PRIVATE one; a stale token that 401s is retried
    unauthenticated (see _fetch_bytes)."""
    return await _fetch_bytes(hass, url, token, "application/octet-stream", 60)


async def async_run_ota(
    hass: HomeAssistant,
    client: OseliaClient,
    gateway: Gateway,
    version: str,
    bundle: bytes,
) -> None:
    """Stream `bundle` to the gateway and wait until it applies.

    Mirrors ota_publish.py: resend the QoS0 command until the device acks via
    ota/state, pace chunks to the CH9120 UART rate, and resend any chunks the device
    NAKs. Progress is shown by the UpdateEntity straight off the device's retained
    ota/state (gateway.ota), so we don't need to report it here.
    """
    device_id = gateway.device_id
    sha = hashlib.sha256(bundle).hexdigest()
    n = (len(bundle) + OTA_CHUNK_SIZE - 1) // OTA_CHUNK_SIZE
    cmd = {"version": version, "size": len(bundle), "chunks": n,
           "chunk_size": OTA_CHUNK_SIZE, "sha256": sha}

    naks: asyncio.Queue = asyncio.Queue()

    @callback
    def _on_nak(missing) -> None:
        if isinstance(missing, list):
            naks.put_nowait(missing)

    unsub = async_dispatcher_connect(hass, SIGNAL_OTA_NAK.format(device_id), _on_nak)

    async def _send(indices) -> None:
        for i in indices:
            payload = struct.pack(">I", i) + bundle[i * OTA_CHUNK_SIZE:(i + 1) * OTA_CHUNK_SIZE]
            client.publish_ota_chunk(device_id, payload)
            await asyncio.sleep(OTA_CHUNK_DELAY)

    def _stage_for_target() -> str | None:
        # Only trust an ota/state that is about OUR target version -- a stale retained
        # state from a previous install (different target) must not be mistaken for
        # progress on this one.
        ota = gateway.ota
        if ota.get("target_version") != version:
            return None
        return ota.get("stage")

    try:
        _LOGGER.info("OSELIA OTA %s -> %s (%d bytes, %d chunks)",
                     device_id, version, len(bundle), n)
        # The command is QoS0 broker->device too, so resend until it acks with a
        # downloading state for our target version.
        acked = False
        for _ in range(OTA_CMD_RETRIES):
            client.publish_ota(device_id, cmd)
            for _ in range(20):
                if _stage_for_target() in ("downloading", "applying", "idle"):
                    acked = True
                    break
                await asyncio.sleep(0.1)
            if acked:
                break
        if not acked:
            raise OtaError("device did not acknowledge the OTA command")

        await _send(range(n))

        # Resend NAK'd chunks until the device applies (or errors / times out).
        deadline = time.monotonic() + OTA_INSTALL_TIMEOUT
        while time.monotonic() < deadline:
            stage = _stage_for_target()
            if stage in ("applying", "idle"):
                _LOGGER.info("OSELIA OTA %s accepted (stage=%s)", device_id, stage)
                return
            if stage == "error":
                raise OtaError("device reported: %s" % gateway.ota.get("error"))
            try:
                missing = await asyncio.wait_for(naks.get(), timeout=3)
            except asyncio.TimeoutError:
                continue
            if missing:
                _LOGGER.debug("OSELIA OTA %s: resending %d NAK'd chunks",
                              device_id, len(missing))
                await _send(missing)
        raise OtaError("OTA timed out")
    finally:
        unsub()
