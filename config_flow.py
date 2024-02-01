"""Adds config flow for Helixer."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.components.file_upload import process_uploaded_file
from .client import (
    HelixerClient,
    HelixerClientAuthenticationError,
    HelixerClientConnectionError,
)
from .const import DOMAIN, LOGGER


class HelixerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Helixer."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.FlowResult:
        """Handle a flow initialized by the user."""
        _errors = {}
        if user_input is not None:
            try:
                # Write content of file instead of path
                with process_uploaded_file(
                    self.hass, user_input.get("certificate")
                ) as file_path:
                    user_input["certificate"] = file_path.read_text()
                with process_uploaded_file(
                    self.hass, user_input.get("key")
                ) as file_path:
                    user_input["key"] = file_path.read_text()
                with process_uploaded_file(
                    self.hass, user_input.get("ca")
                ) as file_path:
                    user_input["ca"] = file_path.read_text()

                user_input["port"] = int(user_input["port"])

                await self._test_connection(user_input)
            except HelixerClientAuthenticationError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "auth"
            except HelixerClientConnectionError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "connection"
            except Exception as exception:  # pylint: disable=broad-except
                LOGGER.warning(exception)
                _errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Helixer - {user_input['endpoint']}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "endpoint", default=(user_input or {}).get("endpoint")
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT
                        ),
                    ),
                    vol.Required(
                        "port", default=(user_input or {}).get("port")
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=65535,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_USERNAME, default=(user_input or {}).get(CONF_USERNAME)
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT
                        ),
                    ),
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        ),
                    ),
                    vol.Required("certificate"): selector.FileSelector(
                        selector.FileSelectorConfig(accept=".crt"),
                    ),
                    vol.Required("key"): selector.FileSelector(
                        selector.FileSelectorConfig(accept=".key"),
                    ),
                    vol.Required("ca"): selector.FileSelector(
                        selector.FileSelectorConfig(accept=".crt"),
                    ),
                }
            ),
            errors=_errors,
        )

    async def _test_connection(self, user_input: dict):
        LOGGER.debug("Testing connection to %s", user_input[CONF_USERNAME])

        client = HelixerClient(
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            mqtt_broker=user_input["endpoint"],
            mqtt_port=user_input["port"],
            key=user_input["key"],
            cert=user_input["certificate"],
            ca=user_input["ca"],
        )
        client.connect_mqtt()
        del client
