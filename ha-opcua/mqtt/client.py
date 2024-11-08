import logging
import socket
import tempfile

import paho.mqtt.client as mqtt

from ..config.const import (
    CONF_MQTT_BROKER,
    CONF_MQTT_CA,
    CONF_MQTT_CERT,
    CONF_MQTT_KEY,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
)

_LOGGER = logging.getLogger(__name__)


class HelixerClientError(Exception):
    """Exception to indicate a general client error."""


class HelixerClientConnectionError(HelixerClientError):
    """Exception to indicate a communication error."""


class HelixerClientAuthenticationError(HelixerClientError):
    """Exception to indicate an authentication error."""


class MQTTClient:
    def __init__(
        self,
        username: str,
        password: str,
        mqtt_broker: str,
        mqtt_port: int,
        key: str = None,
        cert: str = None,
        ca: str = None,
    ) -> None:
        """
        Initialize the MQTT client with the provided credentials and broker information.
        Args:
            username (str): The username for the MQTT broker.
            password (str): The password for the MQTT broker.
            mqtt_broker (str): The address of the MQTT broker.
            mqtt_port (int): The port number of the MQTT broker.
            key (str, optional): The path to the client's private key file. Defaults to None.
            cert (str, optional): The path to the client's certificate file. Defaults to None.
            ca (str, optional): The path to the Certificate Authority file. Defaults to None.
        Returns:
            None
        """

        self._username = username
        self._password = password
        self._mqtt_broker = mqtt_broker
        self._mqtt_port = mqtt_port
        self._key = key
        self._cert = cert
        self._ca = ca
        self._mqtt_client = mqtt.Client(
            client_id="HomeAssistant",
            protocol=mqtt.MQTTv5,
            transport="tcp",
            reconnect_on_failure=True,
        )

        self.store_certs()

        self._mqtt_client.on_connect = on_connect
        self._mqtt_client.on_disconnect = on_disconnect

        self._mqtt_client.username_pw_set(f"{self._username}", f"{self._password}")
        self._mqtt_client.tls_set(
            ca_certs=self._ca_tmp.name,
            certfile=self._cert_tmp.name,
            keyfile=self._key_tmp.name,
            cert_reqs=mqtt.ssl.CERT_NONE,
        )

    def store_certs(self):
        self._key_tmp = tempfile.NamedTemporaryFile(delete=False)
        self._cert_tmp = tempfile.NamedTemporaryFile(delete=False)
        self._ca_tmp = tempfile.NamedTemporaryFile(delete=False)

        self._key_tmp.write(str.encode(self._key))
        self._key_tmp.seek(0)

        self._cert_tmp.write(str.encode(self._cert))
        self._cert_tmp.seek(0)

        self._ca_tmp.write(str.encode(self._ca))
        self._ca_tmp.seek(0)

    async def run_client(self):
        """Start the MQTT client."""
        _LOGGER.debug("Starting MQTT loop")
        self._mqtt_client.loop_start()

    def loop(self):
        """Run the MQTT client loop."""
        _LOGGER.debug("Running MQTT loop")
        self._mqtt_client.loop()

    def connect_mqtt(self):
        _LOGGER.info(
            "Connecting to MQTT broker %s:%s", self._mqtt_broker, self._mqtt_port
        )

        try:
            code = self._mqtt_client.connect(
                host=self._mqtt_broker, port=self._mqtt_port, clean_start=True
            )
            self._mqtt_client.loop()

            return code
        except socket.error as exception:
            _LOGGER.error(
                "Could not connect to MQTT broker %s:%s reason: %s",
                self._mqtt_broker,
                self._mqtt_port,
                exception,
            )

        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.warning(exception)

        return -1

    def disconnect_mqtt(self):
        """Disconnect from the MQTT broker."""
        _LOGGER.debug(
            "Disconnecting from MQTT broker %s:%s", self._mqtt_broker, self._mqtt_port
        )
        if self._mqtt_client:
            self._mqtt_client.disconnect()

    def publish(self, topic: str, payload):
        """Publish a message to a topic."""
        _LOGGER.debug("Publishing %s to topic %s", payload, topic)

        try:
            self._mqtt_client.publish(topic=topic, payload=payload.SerializeToString())
        except socket.error as exception:
            _LOGGER.error("Could not publish to topic %s reason: %s", topic, exception)
            raise HelixerClientConnectionError(
                "Could not publish to topic"
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.warning(exception)
            raise HelixerClientError("Could not publish to topic") from exception

    def close(self):
        """Destructor to clean up resources."""
        _LOGGER.debug("mqtt Destructor called")
        self.disconnect_mqtt()
        self._key_tmp.close()
        self._cert_tmp.close()
        self._ca_tmp.close()


def on_connect(client, userdata, flags, reason_code, properties):
    _LOGGER.debug("Connected with result code " + str(reason_code))


def on_disconnect(client, userdata, flags, reason_code):
    _LOGGER.debug("Disconnected with result code " + str(reason_code))


async def get_mqtt_client(conf) -> MQTTClient:
    """Get an MQTT client."""
    return MQTTClient(
        conf.get(CONF_MQTT_USERNAME),
        conf.get(CONF_MQTT_PASSWORD),
        conf.get(CONF_MQTT_BROKER),
        conf.get(CONF_MQTT_PORT),
        conf.get(CONF_MQTT_KEY),
        conf.get(CONF_MQTT_CERT),
        conf.get(CONF_MQTT_CA),
    )
