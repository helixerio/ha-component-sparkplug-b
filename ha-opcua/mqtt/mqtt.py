import asyncio
import json
import logging
import queue
import threading
import time
from contextlib import suppress
from datetime import datetime

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, State, callback

from ..config.const import (
    DOMAIN,
)
from . import sparkplugb_pb2
from .client import MQTTClient

_LOGGER = logging.getLogger(__name__)


class MQTTThread(threading.Thread):
    def __init__(
        self,
        hass,
        client: MQTTClient,
        base_topic: str,
    ) -> None:
        threading.Thread.__init__(self, name=DOMAIN)
        self._client = client
        self._base_topic = base_topic
        self.queue: queue.SimpleQueue[threading.Event | Event | None] = (
            queue.SimpleQueue()
        )
        self.hass = hass
        self.shutdown = False

        self.hass.loop.create_task(self.connect_client())

    async def connect_client(self):
        while True:
            await asyncio.sleep(5)
            code = self._client.connect_mqtt()
            self._client.loop()
            if code == 0:
                _LOGGER.info("Connected to MQTT broker")
                self.hass.async_create_task(self._client.run_client())
                self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._event_listener)
                break
            else:
                _LOGGER.error(f"Failed to connect to MQTT broker with code {code}")

    @callback
    def _event_listener(self, event):
        """Listen for new messages on the bus and queue them for OPC."""
        item = (time.monotonic(), event)
        if item is None:
            self.shutdown = True
        elif type(item) is tuple:
            _, event = item
            self.queue.put(event)
        else:
            _LOGGER.error("Unknown item in queue: %s", type(item))

    def write_to_mqtt(self):
        with suppress(queue.Empty):
            event = self.queue.get(timeout=None)
            self.state_publisher(event)

    def state_publisher(self, evt: Event) -> None:
        entity_id: str = evt.data["entity_id"]
        new: State = evt.data["new_state"]

        new_state = new.state
        old_state = (
            evt.data["new_state"].state
            if evt.data["old_state"] is None
            else evt.data["old_state"].state
        )

        new_attributes = new.attributes
        old_attributes = (
            evt.data["new_state"].attributes
            if evt.data["old_state"] is None
            else evt.data["old_state"].attributes
        )

        timestamp = int(new.last_updated.timestamp())

        payload = sparkplugb_pb2.Payload()
        payload.timestamp = timestamp

        if new_state != old_state:
            metric = payload.metrics.add()
            metric.name = "state"
            self.cast_value(metric, new_state, timestamp)

        attributes_to_send = {}

        if not old_attributes:
            attributes_to_send = new_attributes
        else:
            for attribute in new_attributes:
                if (
                    attribute not in old_attributes
                    or new_attributes[attribute] != old_attributes[attribute]
                ):
                    attributes_to_send[attribute] = new_attributes[attribute]

        for attribute in attributes_to_send:
            metric = payload.metrics.add()

            if type(attributes_to_send[attribute]) is dict:
                for sub_attribute in attributes_to_send[attribute]:
                    metric = payload.metrics.add()
                    metric.name = f"attributes/{attribute}.{sub_attribute}"
                    self.add_metric_value(
                        metric, attributes_to_send[attribute][sub_attribute], timestamp
                    )

            elif type(attributes_to_send[attribute]) is list:
                for i, item in enumerate(attributes_to_send[attribute]):
                    metric = payload.metrics.add()
                    metric.name = f"attributes/{attribute}.{i}"
                    self.add_metric_value(metric, item, timestamp)
            else:
                metric = payload.metrics.add()
                metric.name = f"attributes/{attribute}"
                self.add_metric_value(metric, attributes_to_send[attribute], timestamp)

        if payload.metrics.__len__() > 0:
            topic = f"spBv1.0/homeassistant/DDATA/{self._base_topic}/{entity_id.replace('.', '/')}"
            self._client.publish(topic, payload)

    def add_metric_value(self, metric, value, timestamp):
        if isinstance(value, str):
            metric.string_value = value
            if value.lower() in ["true", "false"]:
                metric.boolean_value = bool(value)
        elif isinstance(value, int):
            metric.int_value = value
        elif isinstance(value, float):
            metric.float_value = value
        elif isinstance(value, bool):
            metric.boolean_value = value
        elif isinstance(value, list):
            if len(value) > 0:
                metric.string_value = json.dumps(value)
        elif isinstance(value, dict):
            if len(value) > 0:
                metric.string_value = json.dumps(value)
        elif isinstance(value, datetime):
            metric.string_value = value.isoformat()
        else:
            _LOGGER.warning(f"Unsupported type {type(value)} for value {value}")

        metric.timestamp = int(timestamp * 1000)

    def cast_value(self, metric, value: str, timestamp) -> str | int | float | bool:
        _LOGGER.debug(f"Cast value {value} to {type(value)}")

        if value.lower() in ["true", "false"]:
            metric.bool_value = bool(value)
        elif value.isdigit():
            metric.int_value = int(value)
        elif value.replace(".", "", 1).isdigit():
            metric.float_value = float(value)
        else:
            metric.string_value = value

        metric.timestamp = int(timestamp * 1000)

    def run(self):
        """Process incoming events."""
        while not self.shutdown:
            self.write_to_mqtt()

        self._client.disconnect_mqtt()
        self._client.close()
