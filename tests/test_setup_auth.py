from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from unfurled.helpers.exceptions import AuthenticationError

from uc_intg_custom_select import setup


class FakeRemote:
    instances = []

    def __init__(self, remote_url, *, pin=None, wake_if_asleep=True):
        self.remote_url = remote_url
        self.pin = pin
        self.wake_if_asleep = wake_if_asleep
        self.auth = SimpleNamespace(create_key=AsyncMock(return_value="generated-api-key"))
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_create_core_api_key_from_web_configurator_pin(monkeypatch):
    FakeRemote.instances.clear()
    monkeypatch.setattr(setup, "Remote", FakeRemote)
    monkeypatch.setattr(setup.secrets, "token_hex", lambda _size: "a1b2c3")

    result = await setup.create_core_api_key_from_pin(
        "http://remote.local/api/", "123456"
    )

    assert result == "generated-api-key"
    remote = FakeRemote.instances[0]
    assert remote.remote_url == "http://remote.local/api/"
    assert remote.pin == "123456"
    assert remote.wake_if_asleep is False
    remote.auth.create_key.assert_awaited_once_with("UC Custom Select a1b2c3")


@pytest.mark.asyncio
async def test_create_core_api_key_requires_pin():
    with pytest.raises(AuthenticationError, match="PIN is required"):
        await setup.create_core_api_key_from_pin("http://remote.local/api/", "")


@pytest.mark.asyncio
async def test_empty_generated_key_is_rejected(monkeypatch):
    class EmptyKeyRemote(FakeRemote):
        def __init__(self, remote_url, *, pin=None, wake_if_asleep=True):
            super().__init__(remote_url, pin=pin, wake_if_asleep=wake_if_asleep)
            self.auth.create_key = AsyncMock(return_value="")

    monkeypatch.setattr(setup, "Remote", EmptyKeyRemote)

    with pytest.raises(AuthenticationError, match="empty Core API key"):
        await setup.create_core_api_key_from_pin(
            "http://remote.local/api/", "123456"
        )
