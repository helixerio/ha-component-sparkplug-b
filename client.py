"""Helixe Client."""
import paho.mqtt.client as mqtt
import socket
from .const import LOGGER
import tempfile


class HelixerClientError(Exception):
    """Exception to indicate a general client error."""


class HelixerClientConnectionError(HelixerClientError):
    """Exception to indicate a communication error."""


class HelixerClientAuthenticationError(HelixerClientError):
    """Exception to indicate an authentication error."""


class HelixerClient:
    """Helixer API Client."""

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
        self._username = username
        self._password = password
        self._mqtt_broker = mqtt_broker
        self._mqtt_port = mqtt_port
        self._key = key
        self._key_tmp = tempfile.NamedTemporaryFile()
        self._cert = cert
        self._cert_tmp = tempfile.NamedTemporaryFile()
        self._ca = ca
        self._ca_tmp = tempfile.NamedTemporaryFile()
        self._mqtt_client = mqtt.Client()

        self._key_tmp.write(str.encode(self._key))
        self._key_tmp.seek(0)

        self._cert_tmp.write(str.encode(self._cert))
        self._cert_tmp.seek(0)

        self._ca_tmp.write(str.encode(self._ca))
        self._ca_tmp.seek(0)

    def connect_mqtt(self):
        """Connect to the MQTT broker."""
        LOGGER.debug(
            "Connecting to MQTT broker %s:%s", self._mqtt_broker, self._mqtt_port
        )
        try:
            if self._username and self._password:
                LOGGER.debug("Authenticating to MQTT broker as %s", self._username)
                self._mqtt_client.username_pw_set(self._username, self._password)
            if self._key and self._cert:
                LOGGER.debug(
                    "Using client certificate and key stored in %s and %s",
                    self._cert_tmp.name,
                    self._key_tmp.name,
                )
                self._mqtt_client.tls_set(
                    ca_certs=self._ca_tmp.name,
                    certfile=self._cert_tmp.name,
                    keyfile=self._key_tmp.name,
                )

            self._mqtt_client.connect(self._mqtt_broker, self._mqtt_port)
        except socket.error as exception:
            LOGGER.error(
                "Could not connect to MQTT broker %s:%s reason: %s",
                self._mqtt_broker,
                self._mqtt_port,
                exception,
            )
            raise HelixerClientConnectionError(
                "Could not connect to MQTT broker"
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            LOGGER.warning(exception)
            raise HelixerClientError("Could not connect to MQTT broker") from exception
        else:
            LOGGER.debug(
                "Connected to MQTT broker %s:%s", self._mqtt_broker, self._mqtt_port
            )

    def disconnect_mqtt(self):
        """Disconnect from the MQTT broker."""
        LOGGER.debug(
            "Disconnecting from MQTT broker %s:%s", self._mqtt_broker, self._mqtt_port
        )
        if self._mqtt_client:
            self._mqtt_client.disconnect()

    def publish(self, topic: str, payload):
        """Publish a message to a topic."""

        if not self._mqtt_client:
            raise HelixerClientConnectionError("Not connected to MQTT broker")

        LOGGER.debug("Publishing %s to topic %s", payload, topic)
        self._mqtt_client.publish(topic=topic, payload=payload.SerializeToString())

    def __del__(self):
        """Destructor to clean up resources."""
        LOGGER.debug("HelixerClient Destructor called")
        self.disconnect_mqtt()
        self._key_tmp.close()
        self._cert_tmp.close()
        self._ca_tmp.close()
