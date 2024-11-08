"""Support for sending data to Helixer."""

from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import event as event_helper
from homeassistant.helpers.typing import ConfigType

from .config.const import (
    COMPONENT_CONFIG_SCHEMA_CONNECTION,
    CONF_RETRY_COUNT,
    DOMAIN,
    RETRY_INTERVAL,
    RETRY_MESSAGE,
)
from .mqtt import MQTTThread, get_mqtt_client
from .opcua import OPCThread, get_opcua_server

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: COMPONENT_CONFIG_SCHEMA_CONNECTION},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the HA-opcua component."""
    _LOGGER.info("Setting up OPCUA component")
    conf = config[DOMAIN]
    try:
        opcua = await get_opcua_server(conf)
    except Exception as e:
        _LOGGER.error(RETRY_MESSAGE, e)
        event_helper.call_later(
            hass, RETRY_INTERVAL, lambda _: _retry_setup(hass, config)
        )
        return True

    try:
        mqtt = await get_mqtt_client(conf)
    except Exception as e:
        _LOGGER.error(RETRY_MESSAGE, e)
        event_helper.call_later(
            hass, RETRY_INTERVAL, lambda _: _retry_setup(hass, config)
        )
        return True

    _LOGGER.info("Created OPCUA server: %s", opcua.server.endpoint.geturl())

    max_tries = conf.get(CONF_RETRY_COUNT)

    hass.data[DOMAIN] = {
        "opcua": OPCThread(hass, opcua, max_tries),
        "mqtt": MQTTThread(hass, mqtt, "helixer"),
    }

    hass.data[DOMAIN]["opcua"].start()
    hass.data[DOMAIN]["mqtt"].start()

    def shutdown(event):
        """Shut down the thread."""
        hass.data[DOMAIN]["opcua"].queue.put(None)
        hass.data[DOMAIN]["mqtt"].queue.put(None)

        hass.data[DOMAIN]["opcua"].join()
        hass.data[DOMAIN]["mqtt"].join()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown)

    return True


def _retry_setup(hass: HomeAssistant, config: ConfigType) -> None:
    async_setup(hass, config)
