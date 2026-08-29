"""Integration API compatibility helpers for large image-backed Select payloads."""

import logging
from typing import Any

import websockets
from ucapi.api import IntegrationAPI
from websockets.exceptions import ConnectionClosedOK

_LOG = logging.getLogger(__name__)

# The Remote has historically been sensitive to large single WebSocket frames during
# integration setup/state transfer. Keep the logical JSON message intact while sending
# it as smaller WebSocket fragments. The receiver reassembles the fragments before JSON
# parsing, so this is transparent to the Core Integration API protocol.
WEBSOCKET_FRAGMENT_SIZE = 16 * 1024


class FragmentingIntegrationAPI(IntegrationAPI):
    """IntegrationAPI variant that fragments large outgoing text messages."""

    async def _ws_producer(self, websocket: Any, ctx: Any) -> None:
        """Route outgoing messages, fragmenting large text frames when necessary."""
        try:
            while True:
                msg = await ctx.outgoing.get()
                if msg is None:
                    break

                if isinstance(msg, str) and len(msg) > WEBSOCKET_FRAGMENT_SIZE:
                    fragments = tuple(
                        msg[offset : offset + WEBSOCKET_FRAGMENT_SIZE]
                        for offset in range(0, len(msg), WEBSOCKET_FRAGMENT_SIZE)
                    )
                    _LOG.debug(
                        "[%s] Sending %d-character Integration API message in %d fragments",
                        getattr(websocket, "remote_address", "remote"),
                        len(msg),
                        len(fragments),
                    )
                    await websocket.send(fragments)
                else:
                    await websocket.send(msg)
        except (ConnectionClosedOK, websockets.exceptions.ConnectionClosedError):
            pass
