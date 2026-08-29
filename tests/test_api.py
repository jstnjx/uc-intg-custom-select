import asyncio
from types import SimpleNamespace

import pytest

from uc_intg_custom_select.api import FragmentingIntegrationAPI, WEBSOCKET_FRAGMENT_SIZE


class FakeWebSocket:
    def __init__(self):
        self.remote_address = ("127.0.0.1", 1234)
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


@pytest.mark.asyncio
async def test_large_message_is_fragmented_without_changing_payload():
    api = FragmentingIntegrationAPI(asyncio.get_running_loop())
    websocket = FakeWebSocket()
    ctx = SimpleNamespace(outgoing=asyncio.Queue())
    message = "x" * (WEBSOCKET_FRAGMENT_SIZE * 3 + 123)
    await ctx.outgoing.put(message)
    await ctx.outgoing.put(None)

    await api._ws_producer(websocket, ctx)

    assert len(websocket.sent) == 1
    fragments = websocket.sent[0]
    assert not isinstance(fragments, str)
    assert "".join(fragments) == message
    assert all(len(fragment) <= WEBSOCKET_FRAGMENT_SIZE for fragment in fragments)
    assert len(fragments) == 4


@pytest.mark.asyncio
async def test_small_message_is_sent_as_single_text_frame():
    api = FragmentingIntegrationAPI(asyncio.get_running_loop())
    websocket = FakeWebSocket()
    ctx = SimpleNamespace(outgoing=asyncio.Queue())
    await ctx.outgoing.put("small")
    await ctx.outgoing.put(None)

    await api._ws_producer(websocket, ctx)

    assert websocket.sent == ["small"]
