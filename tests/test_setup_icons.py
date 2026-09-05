"""Regression tests for icon-aware setup submissions."""

from types import SimpleNamespace

from ucapi import RequestUserInput

from uc_intg_custom_select.config import CustomSelectConfig, SelectOptionConfig
from uc_intg_custom_select.setup_fast import TimeoutSafeCustomSelectSetupFlow
from uc_intg_custom_select.setup_icons import IconAwareCustomSelectSetupFlow


def _flow() -> IconAwareCustomSelectSetupFlow:
    flow = object.__new__(IconAwareCustomSelectSetupFlow)
    flow._pending_device_config = CustomSelectConfig(
        identifier="apps",
        name="Apps",
        remote_url="http://127.0.0.1/api/",
        api_key="secret",
    )
    flow._option_index = 0
    return flow


async def test_resolved_resource_bypasses_legacy_base64_input(monkeypatch) -> None:
    """Remote resource data must not be fed back through user Base64 validation."""
    flow = _flow()
    resolved = "data:image/png;base64,RESOURCECACHE"

    async def resolve_icon(values, existing):
        assert existing is None
        return "resource", "custom:Netflix.png", resolved

    async def save_option(self, msg):
        assert msg.input_values["image_base64"] == ""
        self._pending_device_config.options.append(
            SelectOptionConfig(
                label="Netflix",
                image_base64="",
                target_entity_id="hass.main.media_player.tv",
                command_id="media_player.select_source",
                params={"source": "Netflix"},
            )
        )
        return None

    flow._resolve_selected_icon = resolve_icon
    monkeypatch.setattr(
        TimeoutSafeCustomSelectSetupFlow,
        "handle_additional_configuration_response",
        save_option,
    )

    msg = SimpleNamespace(
        input_values={
            "icon_source": "resource",
            "resource_icon": "Netflix.png",
            "option_label": "Netflix",
            "image_base64": "",
            "target_entity_id": "hass.main.media_player.tv",
            "command_id": "media_player.select_source",
            "command_params": '{"source":"Netflix"}',
        }
    )
    result = await flow.handle_additional_configuration_response(msg)

    assert result is None
    saved = flow._pending_device_config.options[0]
    assert saved.icon == "custom:Netflix.png"
    assert saved.image_base64 == resolved


async def test_icon_validation_error_reopens_option_screen(monkeypatch) -> None:
    """An invalid icon should no longer abort the complete setup flow."""
    flow = _flow()

    async def resolve_icon(values, existing):
        raise ValueError("Unknown built-in UC icon: uc:not-real")

    flow._resolve_selected_icon = resolve_icon
    flow._build_option_retry_screen = lambda error, values: RequestUserInput(
        {"en": "Retry"},
        [
            {
                "id": "error",
                "label": {"en": "Error"},
                "field": {"label": {"value": {"en": error}}},
            }
        ],
    )

    async def must_not_save(self, msg):
        raise AssertionError("legacy option saver must not run after icon validation failure")

    monkeypatch.setattr(
        TimeoutSafeCustomSelectSetupFlow,
        "handle_additional_configuration_response",
        must_not_save,
    )

    msg = SimpleNamespace(
        input_values={
            "icon_source": "uc",
            "uc_icon": "uc:not-real",
            "option_label": "Test",
            "target_entity_id": "hass.main.media_player.tv",
            "command_id": "media_player.select_source",
            "command_params": "{}",
        }
    )
    result = await flow.handle_additional_configuration_response(msg)

    assert isinstance(result, RequestUserInput)
    assert "Unknown built-in UC icon" in result.settings[0]["field"]["label"]["value"]["en"]
