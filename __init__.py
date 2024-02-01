"""Custom integration to integrate helixer with Home Assistant."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components import mqtt
from homeassistant.components.mqtt import valid_publish_topic
from .client import HelixerClient
from .listener import HelixerListener
from .const import DOMAIN, LOGGER, DOMAIN, LOGGER
from homeassistant.helpers.start import async_at_start


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    hass.data.setdefault(DOMAIN, {})

    client = HelixerClient(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data["endpoint"],
        entry.data["port"],
        entry.data["key"],
        entry.data["certificate"],
        entry.data["ca"],
    )

    try:
        client.connect_mqtt()
    except Exception as exception:  # pylint: disable=broad-except
        LOGGER.warning(exception)
        return False

    listener = HelixerListener(client, "helixer")

    async_at_start(hass, listener.ha_started)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_setup_entry(hass, entry)
