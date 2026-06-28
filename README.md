# OSELIA Hearth — Home Assistant integration

[![Validate](https://github.com/vmyronovych/oselia-hearth-di16g-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/vmyronovych/oselia-hearth-di16g-ha/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Release](https://img.shields.io/github/v/release/vmyronovych/oselia-hearth-di16g-ha)](https://github.com/vmyronovych/oselia-hearth-di16g-ha/releases)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

First-party Home Assistant integration for the **OSELIA Hearth (DI16-G)** gateway — a
24 V wall-switch input hub. The device appears under **its own OSELIA integration** (not
the generic MQTT integration) and gains a native firmware **`update`** entity for OTA.

> Firmware and the provisioning installer live in
> **[vmyronovych/oselia-hearth-di16g-firmware](https://github.com/vmyronovych/oselia-hearth-di16g-firmware)**
> (design contract: [`INTEGRATION_SPEC.md`](https://github.com/vmyronovych/oselia-hearth-di16g-firmware/blob/main/homeassistant/INTEGRATION_SPEC.md);
> OTA core: [`OTA_SPEC.md`](https://github.com/vmyronovych/oselia-hearth-di16g-firmware/blob/main/firmware/OTA_SPEC.md)).
> Hardware and system architecture live in **[vmyronovych/oselia](https://github.com/vmyronovych/oselia)**.

## Install

### HACS (recommended)

1. In Home Assistant, open **HACS** (sidebar) → top-right **⋮** → **Custom repositories**.
2. Paste `https://github.com/vmyronovych/oselia-hearth-di16g-ha`, set category **Integration**, click **Add**, then close the dialog.
3. **Download the integration into Home Assistant:**
   1. In HACS, search for **OSELIA Hearth** and open its page (it shows up after step 2).
   2. Click **Download** (bottom-right), keep the latest version, and confirm **Download**.
      This copies the files into `config/custom_components/oselia` — it does **not** load them yet.
   3. **Restart Home Assistant** so it loads the new integration:
      **Settings → System → ⏻ (top-right) → Restart Home Assistant**
      (or Developer Tools → **Actions** → run `homeassistant.restart`).
4. After the restart: **Settings → Devices & Services → Add integration**, search
   **OSELIA Hearth**, and point it at your broker.

Updates then arrive in HACS automatically on each new release (download the update in HACS,
then restart HA again — same as step 3).

#### Don't have HACS yet?

HACS is a one-time install (it's the store this integration is distributed through).

1. **Download HACS** onto the HA host:
   - **HA OS / Supervised** — open the **Terminal & SSH** add-on and run:
     ```sh
     wget -O - https://get.hacs.xyz | bash -
     ```
   - **Docker / Container** — run the same script *inside* the HA container:
     ```sh
     docker exec -it homeassistant bash -c "wget -O - https://get.hacs.xyz | bash -"
     ```
     (replace `homeassistant` with your container name)
   - Either way it drops HACS into `config/custom_components/hacs`.
2. **Restart Home Assistant**, then hard-refresh your browser (Ctrl/Cmd-Shift-R).
3. **Settings → Devices & Services → Add integration → HACS**, accept the prompts.
4. **Authorize with GitHub**: open <https://github.com/login/device> and enter the code HACS shows.
5. HACS now appears in the sidebar — continue from step 1 above.

> Full upstream guide: <https://hacs.xyz/docs/use/download/download/>.

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
- **Diagnostics** — uptime, free memory, temperature, reconnects, dropped events, input
  boards (+ boards responding), board addresses, last input, IP, Ethernet link.
- **Per-MCP health** (firmware ≥ 0.7.0) — a **"Board N MCP"** connectivity sensor and a
  **"Board N MCP error"** sensor (state = error code, with the raw detail/fail/recovery
  counts as attributes) for every input board, so a single down chip is visible without
  hiding the others' inputs.
- **Root-cause Diagnostics entity** — one **"Diagnostics"** sensor whose state is the
  health summary (`ok`/`degraded`/`mcp_fault`/`net_fault`) and whose *attributes* are the
  full structured `diag/state` blob (per-board MCP, counters, `reset_cause`, and a
  `recent[]` fault timeline). This is the canonical, copy-pasteable export artifact.
- **Fault timeline** — a **"Fault"** `event` entity that fires on each `diag/event`, so
  faults appear in the HA **logbook** as a timeline, and **recovery counters**
  (`INT stuck events`, `I2C bus recoveries`, `MCP resets`) as `total_increasing` sensors
  for long-term statistics.
- **Controls** — Restart / Identify buttons; gesture-timing numbers; log-level select.
- **Firmware update** — native OTA card; `latest_version` from a GitHub release feed.
  OTA is **implemented and hardware-verified end to end** (download→verify→apply→
  boot-confirm, with auto-revert on a bad image), driven from the `update` card.

> **Firmware coupling.** The per-MCP health, counters, `reset_cause`, fault timeline, and
> the Download-Diagnostics richness require **firmware ≥ 0.7.0**. On older firmware those
> fields are simply absent and the corresponding entities stay empty/unknown — the
> integration still works (the wire contract is additive).

## Diagnose a problem & export it to Claude

When something goes wrong but MQTT is still up, the root cause is visible in HA and
exportable for firmware debugging:

1. **One-click (recommended):** the Hearth **device page → ⋮ → Download diagnostics**
   produces a redacted JSON (broker secrets stripped) with the full `diag/state` blob,
   per-board MCP health, counters, `reset_cause`, and the `recent[]` fault timeline. Send
   that file to Claude.
2. **Fastest:** **Developer Tools → States →** the **Diagnostics** entity → copy its
   attributes JSON.
3. **Trend:** the History/Statistics of the counter sensors (e.g. *INT stuck events*)
   shows how often a fault recurs over time.

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
