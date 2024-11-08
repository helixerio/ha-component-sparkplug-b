"""Constants."""

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

CONF_OPCUA_ENDPOINT = "opcua_endpoint"
CONF_OPCUA_NAMESPACE = "opcua_namespace"
CONF_MQTT_USERNAME = "mqtt_username"
CONF_MQTT_PASSWORD = "mqtt_password"
CONF_MQTT_BROKER = "mqtt_broker"
CONF_MQTT_PORT = "mqtt_port"
CONF_MQTT_KEY = "mqtt_key"
CONF_MQTT_CERT = "mqtt_cert"
CONF_MQTT_CA = "mqtt_ca"


CONF_RETRY_COUNT = "max_retries"

DEFAULT_ENDPOINT = "opc.tcp://0.0.0.0:4840/haopcua/server/"
DEFAULT_NAMESPACE = "https://opcua.example.com"


DOMAIN = "haopcua"

RETRY_INTERVAL = 60  # seconds
RETRY_DELAY = 20
RETRY_MESSAGE = f"%s Retrying in {RETRY_INTERVAL} seconds."

EVENT_NEW_STATE = "new_state"

COMPONENT_CONFIG_SCHEMA_CONNECTION = {
    vol.Optional(CONF_OPCUA_ENDPOINT, default=DEFAULT_ENDPOINT): cv.string,
    vol.Optional(CONF_OPCUA_NAMESPACE, default=DEFAULT_NAMESPACE): cv.string,
    vol.Required(CONF_MQTT_USERNAME): cv.string,
    vol.Required(CONF_MQTT_PASSWORD): cv.string,
    vol.Required(CONF_MQTT_BROKER): cv.string,
    vol.Required(CONF_MQTT_PORT): cv.port,
    vol.Optional(CONF_MQTT_KEY): cv.string,
    vol.Optional(CONF_MQTT_CERT): cv.string,
    vol.Optional(CONF_MQTT_CA): cv.string,
}
