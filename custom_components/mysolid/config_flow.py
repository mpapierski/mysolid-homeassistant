"""Config flow for MySolid."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MySolidClient, default_device_name, generate_device_id
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_PUSH_ENABLED,
    CONF_PUSH_RECONNECT_SECONDS,
    CONF_REGION,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_PUSH_ENABLED,
    DEFAULT_PUSH_RECONNECT_SECONDS,
    DEFAULT_REGION,
    DOMAIN,
    MAX_POLL_INTERVAL_SECONDS,
    MAX_PUSH_RECONNECT_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
    MIN_PUSH_RECONNECT_SECONDS,
    REGION_CS,
    REGION_CUSTOM,
    REGION_PL,
    config_entry_unique_id,
    resolve_host,
)
from .exceptions import MySolidApiError, MySolidAuthError


def _title_for(email: str) -> str:
    return f"MySolid ({email})"


async def _async_validate_input(hass, user_input: dict[str, Any]) -> dict[str, Any]:
    region = user_input[CONF_REGION]
    host = resolve_host(region, user_input.get("host"))
    email = str(user_input[CONF_EMAIL]).strip()
    password = str(user_input[CONF_PASSWORD])
    device_id = generate_device_id()
    device_name = default_device_name()

    client = MySolidClient(
        host=host,
        email=email,
        device_id=device_id,
        device_name=device_name,
        session=async_get_clientsession(hass),
    )
    await client.login(email, password)
    return {
        "host": host,
        CONF_REGION: region,
        CONF_EMAIL: email,
        CONF_PASSWORD: password,
        CONF_DEVICE_ID: device_id,
        CONF_DEVICE_NAME: device_name,
        CONF_PUSH_ENABLED: DEFAULT_PUSH_ENABLED,
        CONF_POLL_INTERVAL_SECONDS: DEFAULT_POLL_INTERVAL_SECONDS,
        CONF_PUSH_RECONNECT_SECONDS: DEFAULT_PUSH_RECONNECT_SECONDS,
    }


class MySolidConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> MySolidOptionsFlow:
        return MySolidOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        return await self._async_step_connect("user", user_input)

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        return await self._async_step_connect("reconfigure", user_input)

    async def _async_step_connect(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await _async_validate_input(self.hass, user_input)
            except MySolidAuthError:
                errors["base"] = "invalid_auth"
            except MySolidApiError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["host"] = "required"
            else:
                unique_id = config_entry_unique_id(data["host"], data[CONF_EMAIL])
                await self.async_set_unique_id(unique_id, raise_on_progress=False)
                title = _title_for(data[CONF_EMAIL])
                if self.source == SOURCE_RECONFIGURE:
                    entry = self._get_reconfigure_entry()
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=unique_id,
                        title=title,
                        data_updates=data,
                    )
                self._abort_if_unique_id_configured(updates=data)
                return self.async_create_entry(title=title, data=data)

        defaults = user_input or {}
        if step_id == "reconfigure":
            defaults = {**self._get_reconfigure_entry().data, **defaults}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_REGION,
                    default=defaults.get(CONF_REGION, DEFAULT_REGION),
                ): vol.In(
                    {
                        REGION_PL: "Poland",
                        REGION_CS: "Czech Republic",
                        REGION_CUSTOM: "Custom host",
                    }
                ),
                vol.Optional("host", default=defaults.get("host", "")): str,
                vol.Required(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): str,
                vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            }
        )
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)


class MySolidOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PUSH_ENABLED,
                        default=options.get(
                            CONF_PUSH_ENABLED,
                            data.get(CONF_PUSH_ENABLED, DEFAULT_PUSH_ENABLED),
                        ),
                    ): bool,
                    vol.Required(
                        CONF_POLL_INTERVAL_SECONDS,
                        default=options.get(
                            CONF_POLL_INTERVAL_SECONDS,
                            data.get(
                                CONF_POLL_INTERVAL_SECONDS,
                                DEFAULT_POLL_INTERVAL_SECONDS,
                            ),
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_POLL_INTERVAL_SECONDS,
                            max=MAX_POLL_INTERVAL_SECONDS,
                        ),
                    ),
                    vol.Required(
                        CONF_PUSH_RECONNECT_SECONDS,
                        default=options.get(
                            CONF_PUSH_RECONNECT_SECONDS,
                            data.get(
                                CONF_PUSH_RECONNECT_SECONDS,
                                DEFAULT_PUSH_RECONNECT_SECONDS,
                            ),
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_PUSH_RECONNECT_SECONDS,
                            max=MAX_PUSH_RECONNECT_SECONDS,
                        ),
                    ),
                }
            ),
        )
