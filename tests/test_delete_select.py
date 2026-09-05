"""Regression tests for deleting Custom Selects from the Remote."""

from types import SimpleNamespace

from ucapi import SetupComplete, SetupError

from uc_intg_custom_select.config import CustomSelectConfig
from uc_intg_custom_select.setup_delete import CoreCleanupCustomSelectSetupFlow


class _ConfigStore:
    def __init__(self, config: CustomSelectConfig) -> None:
        self.config = config
        self.removed: list[str] = []

    def get(self, device_id: str):
        return self.config if device_id == self.config.identifier else None

    def remove(self, device_id: str) -> bool:
        if device_id != self.config.identifier:
            return False
        self.removed.append(device_id)
        return True


def _flow(config: CustomSelectConfig) -> CoreCleanupCustomSelectSetupFlow:
    flow = object.__new__(CoreCleanupCustomSelectSetupFlow)
    flow.config = _ConfigStore(config)
    flow._quick_operation = ""
    flow._pending_device_config = None
    flow._selected_config_id = None
    return flow


async def test_remove_deletes_core_entity_before_local_config(monkeypatch) -> None:
    config = CustomSelectConfig(
        identifier="apps",
        name="Apps",
        remote_url="http://127.0.0.1/api/",
        api_key="secret",
    )
    flow = _flow(config)
    order: list[str] = []

    async def no_sleep(_seconds: float) -> None:
        return None

    async def delete_core(_config: CustomSelectConfig) -> None:
        order.append("core")

    original_remove = flow.config.remove

    def remove_local(device_id: str) -> bool:
        order.append("local")
        return original_remove(device_id)

    monkeypatch.setattr("uc_intg_custom_select.setup_delete.asyncio.sleep", no_sleep)
    flow._delete_configured_core_entity = delete_core
    flow.config.remove = remove_local

    result = await flow._handle_configuration_mode(
        SimpleNamespace(input_values={"action": "remove", "choice": "apps"})
    )

    assert isinstance(result, SetupComplete)
    assert order == ["core", "local"]
    assert flow.config.removed == ["apps"]


async def test_remove_keeps_local_config_when_core_delete_fails(monkeypatch) -> None:
    config = CustomSelectConfig(
        identifier="apps",
        name="Apps",
        remote_url="http://127.0.0.1/api/",
        api_key="secret",
    )
    flow = _flow(config)

    async def no_sleep(_seconds: float) -> None:
        return None

    async def delete_core(_config: CustomSelectConfig) -> None:
        raise RuntimeError("Core unavailable")

    monkeypatch.setattr("uc_intg_custom_select.setup_delete.asyncio.sleep", no_sleep)
    flow._delete_configured_core_entity = delete_core

    result = await flow._handle_configuration_mode(
        SimpleNamespace(input_values={"action": "remove", "choice": "apps"})
    )

    assert isinstance(result, SetupError)
    assert flow.config.removed == []


async def test_core_cleanup_uses_configured_entity_delete_endpoint(monkeypatch) -> None:
    config = CustomSelectConfig(
        identifier="apple_tv_apps",
        name="Apple TV Apps",
        remote_url="http://127.0.0.1/api/",
        api_key="secret",
    )
    calls: list[tuple[str, str]] = []

    class FakeCoreAPI:
        def __init__(self, remote_url: str, *, api_key: str) -> None:
            assert remote_url == config.remote_url
            assert api_key == config.api_key

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get_entities(self, *, limit: int, page: int):
            assert limit == 100
            if page == 1:
                return [
                    {"entity_id": "custom-select.main.select.apple_tv_apps"},
                    {"entity_id": "hass.main.light.example"},
                ]
            return []

        async def request(self, method: str, path: str):
            calls.append((method, path))
            return None

    monkeypatch.setattr("uc_intg_custom_select.setup_delete.CoreAPI", FakeCoreAPI)
    flow = object.__new__(CoreCleanupCustomSelectSetupFlow)

    await flow._delete_configured_core_entity(config)

    assert calls == [("DELETE", "entities/custom-select.main.select.apple_tv_apps")]
