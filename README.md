# OSELIA Hearth — Home Assistant integration

[![Validate](https://github.com/vmyronovych/oselia-hearth-di16g/actions/workflows/validate.yml/badge.svg)](https://github.com/vmyronovych/oselia-hearth-di16g/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Release](https://img.shields.io/github/v/release/vmyronovych/oselia-hearth-di16g)](https://github.com/vmyronovych/oselia-hearth-di16g/releases)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

First-party Home Assistant integration for the **OSELIA Hearth (DI16-G)** gateway — a
24 V wall-switch input hub. The device appears under **its own OSELIA integration** (not
the generic MQTT integration) and gains a native firmware **`update`** entity for OTA.

> Firmware, hardware and provisioning live in the main project:
> **[vmyronovych/oselia](https://github.com/vmyronovych/oselia)**
> (design contract: [`INTEGRATION_SPEC.md`](https://github.com/vmyronovych/oselia/blob/main/dib-rp2040-eth-i2c/homeassistant/INTEGRATION_SPEC.md);
> OTA core: [`OTA_SPEC.md`](https://github.com/vmyronovych/oselia/blob/main/dib-rp2040-eth-i2c/firmware/OTA_SPEC.md)).

## Install

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories**.
2. Repository: `https://github.com/vmyronovych/oselia-hearth-di16g`, category **Integration**.
3. Install **OSELIA Hearth**, then restart Home Assistant.
4. **Settings → Devices & Services → Add integration → OSELIA Hearth**, point it at your broker.

Updates then arrive in HACS automatically on each new release.

### Manual

Copy `custom_components/oselia/` into your HA `config/custom_components/`, restart HA, and
add the integration as above.

## How it works

- The integration opens **its own MQTT connection** to the same broker the gateways use
  (it does *not* depend on HA's MQTT integration). One config entry per broker.
- Gateways are discovered from their retained topics (`hearth/<id>/status`,
  `…/diag/state`). Each becomes one HA device under OSELIA.
- The firmware **wire format is unchanged**; the integration owns the entities instead of
  firmware-published MQTT discovery.

## Entities per gateway

- **Events** — one `event` per wall-switch input (`single`/`double`/`long`).
- **Device triggers** — per input `button_short_press` / `button_double_press` /
  `button_long_press`, so they appear in the automation "Device → Trigger" picker.
- **Diagnostics** — uptime, free memory, temperature, reconnects, dropped events, boards
  online, board addresses, last input, IP, Ethernet link.
- **Controls** — Restart / Identify buttons; gesture-timing numbers; log-level select.
- **Firmware update** — native OTA card; `latest_version` from a GitHub release feed.
  OTA is **implemented and hardware-verified end to end** (download→verify→apply→
  boot-confirm, with auto-revert on a bad image), driven from the `update` card.

## Resilience

- **Startup-safe** (paho `connect_async()` — a broker down at HA startup never fails
  setup), **auto-reconnect** with re-subscribe, **availability follows the broker link**,
  a always-available **"Broker connection"** connectivity sensor, and **reload-safe**
  config-entry teardown. Verified against broker restart, extended outage, broker-down
  startup, and reload.

## Releasing

See [`RELEASING.md`](RELEASING.md). In short: create a `v*` GitHub Release and the
`release` workflow stamps the version, zips the component, and attaches `oselia.zip`
(the asset HACS installs).
