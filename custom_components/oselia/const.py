"""Constants for the OSELIA Hearth integration.

See ../../INTEGRATION_SPEC.md for the design contract. The MQTT topic layout here
MUST match the firmware (firmware/src/ha_discovery.py, diag.py) -- it is the stable
wire contract; the integration owns the HA-side entities instead of firmware-published
MQTT discovery.
"""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "oselia"
MANUFACTURER = "OSELIA"
DEFAULT_MODEL = "Hearth (DI16-G)"

# --- broker config-entry keys ---
CONF_BROKER = "broker"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_BASE_TOPIC = "base_topic"
CONF_RELEASE_URL = "release_url"
CONF_GITHUB_TOKEN = "github_token"   # for a PRIVATE GitHub release feed (HA-side only)

DEFAULT_PORT = 1883
# Firmware config.py BASE_TOPIC default. Topics are hearth/<device_id>/...
DEFAULT_BASE_TOPIC = "hearth"

PINS_PER_CHIP = 16
GESTURES = ("single", "double", "long")

PLATFORMS = [
    Platform.EVENT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.UPDATE,
]

# --- dispatcher signals ---
# Fired once when a gateway is first seen on the broker (payload: device_id).
SIGNAL_NEW_GATEWAY = f"{DOMAIN}_new_gateway"
# Fired when a gateway's input/board count is known or grows (per device_id).
SIGNAL_NEW_INPUTS = DOMAIN + "_new_inputs_{}"
# Fired when any of a gateway's state (status/diag/cfg/ota/log) changes (per device_id).
SIGNAL_GATEWAY_UPDATE = DOMAIN + "_update_{}"
# Fired on an input action/gesture (per device_id; payload: (board, pin, gesture)).
SIGNAL_ACTION = DOMAIN + "_action_{}"
# Fired (global, per entry irrelevant) when the broker connection goes up/down.
SIGNAL_CONNECTION = f"{DOMAIN}_connection"
# Fired when the device NAKs missing OTA chunks (per device_id; payload: list[int]).
SIGNAL_OTA_NAK = DOMAIN + "_ota_nak_{}"

# --- OTA transport tuning (must stay compatible with firmware OTA_SPEC.md) ---
OTA_CHUNK_SIZE = 1024          # bytes per ota/data chunk
OTA_CHUNK_DELAY = 0.2          # seconds between chunks (proven clean over the CH9120 UART)
OTA_CMD_RETRIES = 8            # resend the QoS0 command until the device acks
OTA_INSTALL_TIMEOUT = 240      # overall seconds before giving up an install
