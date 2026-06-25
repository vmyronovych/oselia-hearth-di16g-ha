# OSELIA Hearth

First-party Home Assistant integration for the **OSELIA Hearth (DI16-G)** 24 V
wall-switch input gateway. The device appears under its own OSELIA integration (not the
generic MQTT integration) with:

- **Events + device triggers** per wall-switch input (single / double / long).
- **Diagnostics** — uptime, free memory, temperature, reconnects, Ethernet link, and more.
- **Controls** — Restart / Identify, gesture-timing tuning, log level.
- **Firmware OTA** — a native `update` card; hardware-verified end to end with auto-revert.

The integration runs its own MQTT client to the broker (no dependency on HA's MQTT
integration) and is startup-safe, auto-reconnecting, and reload-safe.

After install, restart HA and add it via **Settings → Devices & Services → Add
integration → OSELIA Hearth**.
