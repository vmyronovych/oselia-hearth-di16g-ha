"""Config flow for the OSELIA Hearth integration.

One entry per broker. Validation connects to the broker (in the executor) and waits
for CONNACK; the gateway itself isn't an HTTP endpoint, so DHCP discovery only
pre-fills and still asks for broker credentials.
"""
from __future__ import annotations

import logging
from typing import Any

import paho.mqtt.client as mqtt
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import (
    CONF_BASE_TOPIC,
    CONF_BROKER,
    CONF_GITHUB_TOKEN,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_RELEASE_URL,
    CONF_USERNAME,
    DEFAULT_BASE_TOPIC,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _try_connect(host: str, port: int, username: str | None, password: str | None) -> str | None:
    """Return None on success, else an error key ('cannot_connect' / 'invalid_auth')."""
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    else:
        client = mqtt.Client()
    if username:
        client.username_pw_set(username, password or "")
    result: dict[str, int] = {}

    def _on_connect(c, u, flags, reason_code, *args):
        # paho 1.x passes an int rc; paho 2.x passes a ReasonCode (no __int__),
        # whose .value is the numeric code. Normalize to an int either way.
        result["rc"] = int(getattr(reason_code, "value", reason_code))

    client.on_connect = _on_connect
    try:
        client.connect(host, port, keepalive=10)
        client.loop_start()
        # Wait briefly for CONNACK.
        import time

        for _ in range(50):
            if "rc" in result:
                break
            time.sleep(0.1)
    except OSError:
        return "cannot_connect"
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:  # pragma: no cover - defensive
            pass
    rc = result.get("rc")
    if rc is None:
        return "cannot_connect"
    if rc in (4, 5):  # bad username/password / not authorized
        return "invalid_auth"
    if rc != 0:
        return "cannot_connect"
    return None


class OseliaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the OSELIA broker config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OseliaOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_BROKER]
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            err = await self.hass.async_add_executor_job(
                _try_connect,
                host,
                port,
                user_input.get(CONF_USERNAME),
                user_input.get(CONF_PASSWORD),
            )
            if err:
                errors["base"] = err
            else:
                return self.async_create_entry(
                    title=f"OSELIA ({host})", data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_BROKER): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_USERNAME): str,
                vol.Optional(CONF_PASSWORD): str,
                vol.Optional(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """A Hearth gateway grabbed a DHCP lease -- offer to set up its broker."""
        # The device isn't directly addressable for config; we still need broker creds.
        # Use the MAC as a soft unique id so HA doesn't re-prompt for the same unit.
        await self.async_set_unique_id(discovery_info.macaddress, raise_on_progress=False)
        return await self.async_step_user()


class OseliaOptionsFlow(OptionsFlow):
    """Options: the firmware release-feed URL that drives the update entity."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        if user_input is not None:
            # Validate the feed up front so a misconfigured URL/token (private repo
            # without a token, bad token, no published release, missing bundle) fails
            # here with the reason -- instead of silently showing "Up to date" later.
            release_url = (user_input.get(CONF_RELEASE_URL) or "").strip()
            if release_url:
                from .ota import FeedError, async_fetch_manifest

                try:
                    await async_fetch_manifest(
                        self.hass, release_url,
                        user_input.get(CONF_GITHUB_TOKEN) or None,
                    )
                except FeedError as err:
                    errors["base"] = "feed_error"
                    description_placeholders["error"] = str(err)
            if not errors:
                return self.async_create_entry(data=user_input)
            opts = user_input  # re-show the form with what the user just entered
        else:
            opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RELEASE_URL, default=opts.get(CONF_RELEASE_URL, "")
                ): str,
                vol.Optional(
                    CONF_GITHUB_TOKEN, default=opts.get(CONF_GITHUB_TOKEN, "")
                ): str,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )
