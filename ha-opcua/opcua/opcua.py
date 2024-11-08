from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from asyncua import Server, ua
from homeassistant.const import (
    EVENT_STATE_CHANGED,
)
from homeassistant.core import Event, State, callback
from homeassistant.helpers import state as state_helper

from ..config.const import (
    CONF_OPCUA_ENDPOINT,
    CONF_OPCUA_NAMESPACE,
    DOMAIN,
    EVENT_NEW_STATE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class OPCUAServer:
    """A class to hold the OPCUA server and related data."""

    server: Server
    namespace_idx: int
    objects: dict[str, ua.Node] = None
    close: Callable[[], None] = None


async def get_opcua_server(conf) -> OPCUAServer:
    """Create the opcua server"""

    server = Server()
    await server.init()

    server.set_endpoint(conf.get(CONF_OPCUA_ENDPOINT))
    namespace_idx = await server.register_namespace(conf.get(CONF_OPCUA_NAMESPACE))

    def close():
        server.stop()

    return OPCUAServer(server, namespace_idx, {}, close)


class OPCThread(threading.Thread):
    """A threaded event handler class."""

    def __init__(self, hass, opcua, max_tries):
        """Initialize the listener."""
        threading.Thread.__init__(self, name=DOMAIN)
        self.queue: queue.SimpleQueue[threading.Event | Event | None] = (
            queue.SimpleQueue()
        )
        self.opcua = opcua
        self.max_tries = max_tries
        self.write_errors = 0
        self.shutdown = False
        self.hass = hass

        hass.async_create_task(self.run_server(server=self.opcua.server))
        hass.bus.async_listen(EVENT_STATE_CHANGED, self._event_listener)

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

    async def run_server(self, server: OPCUAServer) -> None:
        """Run the OPCUA server."""
        await server.start()

    def write_to_opcua(self):
        """Write the state to the OPCUA server."""
        with suppress(queue.Empty):
            event = self.queue.get(timeout=None)

            if event is None:
                self.shutdown = True
                return None

            state: State | None = event.data.get(EVENT_NEW_STATE)
            if state is None:
                return None

            _state_as_value = None
            try:
                _state_as_value = float(state.state)
            except ValueError:
                try:
                    _state_as_value = float(state_helper.state_as_number(state))
                except ValueError:
                    pass

            if _state_as_value:
                self.write_opc_value(state.object_id, "value", _state_as_value)

            for key, value in state.attributes.items():
                self.write_opc_value(state.object_id, key, value)

    def write_opc_value(self, entity_id, key: str, value: Any):
        """Set the value of a variable in the OPCUA server."""

        if isinstance(value, str):
            value = ua.String(value)
        elif isinstance(value, int):
            value = ua.Int32(value)
        elif isinstance(value, float):
            value = ua.Float(value)
        elif isinstance(value, bool):
            value = ua.Boolean(value)
        elif isinstance(value, list):
            value = ua.Variant()
        elif isinstance(value, datetime):
            value = ua.DateTime(value)
        elif value is None:
            value = ua.Null()
        else:
            _LOGGER.error("Unknown value type %s", type(value))
            return

        entity = self.get_entity_opc_object(entity_id, key)

        if key not in entity["properties"]:
            opc_property = asyncio.run_coroutine_threadsafe(
                self.opcua.objects[entity_id]["folder"].add_variable(
                    self.opcua.namespace_idx, key, value
                ),
                loop=self.hass.loop,
            ).result()

            self.opcua.objects[entity_id]["properties"][key] = opc_property
            return

        opc_property = entity["properties"][key]
        asyncio.run_coroutine_threadsafe(
            opc_property.write_value(value), loop=self.hass.loop
        ).result()

    def get_entity_opc_object(self, entity_id: str, key: str):
        if entity_id not in self.opcua.objects:
            opc_object = asyncio.run_coroutine_threadsafe(
                self.opcua.server.nodes.objects.add_object(
                    self.opcua.namespace_idx, entity_id
                ),
                loop=self.hass.loop,
            ).result()

            self.opcua.objects[entity_id] = {
                "folder": opc_object,
                "properties": {},
            }

        return self.opcua.objects[entity_id]

    def run(self):
        """Process incoming events."""
        while not self.shutdown:
            self.write_to_opcua()

        self.opcua.close()
