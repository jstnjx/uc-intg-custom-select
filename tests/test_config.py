import json
from unittest.mock import Mock

from uc_intg_custom_select.config import CustomSelectConfigManager


def _config_payload(label="Netflix"):
    return {
        "identifier": "apps",
        "name": "Apps",
        "remote_url": "http://remote/api/",
        "api_key": "secret",
        "icon_size": 96,
        "image_alignment": "middle",
        "spacing": 2,
        "label_style": {
            "bold": True,
            "italic": False,
            "underline": False,
            "color": "#ffffff",
            "size": 0,
        },
        "options": [
            {
                "label": label,
                "image_base64": "data:image/png;base64,AAAA",
                "target_entity_id": "hass.main.media_player.tv",
                "command_id": "media_player.select_source",
                "params": {"source": label},
            }
        ],
    }


def test_nested_config_deserialization(tmp_path):
    manager = CustomSelectConfigManager(str(tmp_path))
    config = manager.deserialize_device(_config_payload())

    assert config is not None
    assert config.label_style.bold is True
    assert config.options[0].label == "Netflix"
    assert config.options[0].params == {"source": "Netflix"}


def test_restore_rebuilds_runtime_after_persisting_replacement(tmp_path):
    add_handler = Mock()
    remove_handler = Mock()
    manager = CustomSelectConfigManager(
        str(tmp_path), add_handler=add_handler, remove_handler=remove_handler
    )

    assert manager.restore_from_backup_json(json.dumps([_config_payload("Spotify")]))

    remove_handler.assert_called_once_with(None)
    add_handler.assert_called_once()
    restored = list(manager.all())
    assert len(restored) == 1
    assert restored[0].options[0].label == "Spotify"

    stored = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert stored[0]["options"][0]["label"] == "Spotify"
