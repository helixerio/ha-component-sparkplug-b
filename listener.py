from . import sparkplugb_pb2
from .client import HelixerClient
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, State, callback
from .const import LOGGER


class HelixerListener:
    def __init__(
        self,
        client: HelixerClient,
        base_topic: str,
    ) -> None:
        self._client = client
        self._base_topic = base_topic

    async def _state_publisher(self, evt: Event) -> None:
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
        if type(value) is bool:
            metric.boolean_value = value
        elif type(value) is int:
            metric.int_value = value
        elif type(value) is float:
            metric.float_value = value
        elif type(value) is str:
            metric.string_value = value
        else:
            LOGGER.warning(f"Unsupported type {type(value)} for value {value}")
            metric.string_value = str(value)

        metric.timestamp = int(timestamp * 1000)

    def cast_value(self, metric, value: str, timestamp) -> str | int | float | bool:
        LOGGER.debug(f"Cast value {value} to {type(value)}")

        if value.lower() in ["true", "false"]:
            metric.bool_value = bool(value)
        elif value.isdigit():
            metric.int_value = int(value)
        elif value.replace(".", "", 1).isdigit():
            metric.float_value = float(value)
        else:
            metric.string_value = str(value)

        metric.timestamp = int(timestamp * 1000)

    @callback
    def ha_started(self, ha: HomeAssistant) -> None:
        LOGGER.info("Starting Helixer listener")

        @callback
        def _event_filter(evt: Event) -> bool:
            entity_id: str = evt.data["entity_id"]
            new_state: State | None = evt.data["new_state"]
            if new_state is None:
                return False
            return True

        callback_handler = ha.bus.async_listen(
            EVENT_STATE_CHANGED, self._state_publisher, _event_filter
        )

        @callback
        def _ha_stopping(self) -> None:
            LOGGER.info("Stopping Helixer listener")
            callback_handler()

        ha.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _ha_stopping)
