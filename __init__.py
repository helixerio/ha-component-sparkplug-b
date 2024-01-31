import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.components.mqtt import valid_publish_topic
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.entityfilter import (
    INCLUDE_EXCLUDE_BASE_FILTER_SCHEMA,
    convert_include_exclude_filter,
)
from homeassistant.helpers.start import async_at_start
from homeassistant.helpers.typing import ConfigType

from . import sparkplugb_pb2

CONF_BASE_TOPIC = "base_topic"
CONF_PUBLISH_ATTRIBUTES = "publish_attributes"
CONF_PUBLISH_TIMESTAMPS = "publish_timestamps"

DOMAIN = "helixer"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: INCLUDE_EXCLUDE_BASE_FILTER_SCHEMA.extend(
            {
                vol.Required(CONF_BASE_TOPIC): valid_publish_topic,
                vol.Optional(CONF_PUBLISH_ATTRIBUTES, default=False): cv.boolean,
                vol.Optional(CONF_PUBLISH_TIMESTAMPS, default=False): cv.boolean,
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the MQTT state feed."""
    # Make sure MQTT integration is enabled and the client is available
    if not await mqtt.async_wait_for_mqtt_client(hass):
        _LOGGER.error("MQTT integration is not available")
        return False

    conf: ConfigType = config[DOMAIN]
    publish_filter = convert_include_exclude_filter(conf)
    base_topic: str = conf[CONF_BASE_TOPIC]

    if not base_topic.endswith("/"):
        base_topic = f"{base_topic}/"

    async def _state_publisher(evt: Event) -> None:
        entity_id: str = evt.data["entity_id"]
        new_state: State = evt.data["new_state"]

        payload = sparkplugb_pb2.Payload()
        payload.timestamp = int(new_state.last_updated.timestamp() * 1000)

        metric = payload.metrics.add()
        metric.name = entity_id

        if new_state.state.lower() in ["true", "false"]:
            metric.bool_value = bool(new_state.state)
        elif new_state.state.isdigit():
            metric.int_value = int(new_state.state)
        elif new_state.state.replace(".", "", 1).isdigit():
            metric.float_value = float(new_state.state)
        else:
            metric.string_value = f'"{str(new_state.state)}"'

        metric.timestamp = int(new_state.last_updated.timestamp() * 1000)

        mybase = (
            f"spBv1.0/homeassistant/DDATA/{base_topic}{entity_id.replace('.', '/')}"
        )
        await mqtt.async_publish(hass, mybase, payload.SerializeToString(), 1, True)

    @callback
    def _ha_started(ha: HomeAssistant) -> None:
        @callback
        def _event_filter(evt: Event) -> bool:
            entity_id: str = evt.data["entity_id"]
            new_state: State | None = evt.data["new_state"]
            if new_state is None:
                return False
            if not publish_filter(entity_id):
                return False
            return True

        callback_handler = ha.bus.async_listen(
            EVENT_STATE_CHANGED, _state_publisher, _event_filter
        )

        @callback
        def _ha_stopping(_: Event) -> None:
            callback_handler()

        ha.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _ha_stopping)

    async_at_start(hass, _ha_started)

    return True
