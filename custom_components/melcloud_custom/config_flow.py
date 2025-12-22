"""Config flow for the MELCloud platform."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from http import HTTPStatus
import logging
from typing import Any

from aiohttp import ClientError, ClientResponseError
import pymelcloud
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaFlowFormStep,
    SchemaOptionsFlowHandler,
)

from . import MELCLOUD_SCHEMA, MelCloudAuthentication
from .const import (  # pylint: disable=unused-import
    CONF_LANGUAGE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LANGUAGES,
)

_LOGGER = logging.getLogger(__name__)


async def get_options_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    """Get options schema."""
    return vol.Schema(
        {
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                vol.Coerce(int), vol.Clamp(min=60, max=1800)
            ),
        }
    )


OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(get_options_schema),
}


class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def _create_entry(self, username: str, token: str) -> ConfigFlowResult:
        """Register new entry."""
        await self.async_set_unique_id(username)
        self._abort_if_unique_id_configured({CONF_TOKEN: token})
        return self.async_create_entry(
            title=username,
            data={CONF_TOKEN: token},
        )

    async def _create_client(
        self, user_input: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create client."""
        username = user_input[CONF_USERNAME]
        password = user_input[CONF_PASSWORD]
        language = user_input[CONF_LANGUAGE]

        if password is None:
            raise ValueError(
                "Invalid internal state. Called without password",
            )

        try:
            async with asyncio.timeout(10):
                token = await self._test_authorization(username, password, language)
                if not token:
                    return self._show_form({"base": "invalid_auth"})
                await pymelcloud.get_devices(
                    token,
                    async_get_clientsession(self.hass),
                )

        except ClientResponseError as err:
            if err.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                return self._show_form({"base": "invalid_auth"})
            return self._show_form({"base": "cannot_connect"})
        except (TimeoutError, ClientError):
            return self._show_form({"base": "cannot_connect"})

        return await self._create_entry(username, token)

    async def _test_authorization(
        self, username: str, password: str, language: str
    ) -> str | None:
        """Test authorization with MELCloud."""
        mcauth = MelCloudAuthentication(username, password, LANGUAGES[language])
        if await mcauth.login(self.hass):
            return mcauth.auth_token
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """User initiated config flow."""
        if user_input is None:
            return self._show_form()

        return await self._create_client(user_input)

    async def async_step_import(
        self, import_config: dict[str, Any]
    ) -> ConfigFlowResult:
        """Import a config entry."""
        username = import_config[CONF_USERNAME]
        for unique_id in self._async_current_ids():
            if unique_id == username:
                return self.async_abort(reason="already_imported")
        return await self._create_client(import_config)

    @callback
    def _show_form(self, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        """Show the form to the user."""
        return self.async_show_form(
            step_id="user",
            data_schema=MELCLOUD_SCHEMA,
            errors=errors if errors else {},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle initiation of re-authentication with MELCloud."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-authentication with MELCloud."""
        errors: dict[str, str] = {}

        if user_input is not None:
            reauth_entry = self._get_reauth_entry()
            username = reauth_entry.data.get(CONF_USERNAME)
            if not username:
                # If username not in data, try to get from unique_id
                username = reauth_entry.unique_id
            password = user_input[CONF_PASSWORD]
            language = user_input.get(CONF_LANGUAGE, "EN")

            try:
                async with asyncio.timeout(10):
                    token = await self._test_authorization(username, password, language)
                    if not token:
                        errors["base"] = "invalid_auth"
                    else:
                        return self.async_update_reload_and_abort(
                            reauth_entry,
                            data={CONF_TOKEN: token},
                        )
            except ClientResponseError as err:
                if err.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except (TimeoutError, ClientError):
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_LANGUAGE, default="EN"): vol.In(LANGUAGES.keys()),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SchemaOptionsFlowHandler:
        """Get options flow for this handler."""
        return SchemaOptionsFlowHandler(config_entry, OPTIONS_FLOW)
