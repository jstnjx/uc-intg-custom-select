from uc_intg_custom_select.config import CustomSelectConfigManager


def test_nested_config_deserialization(tmp_path):
    manager = CustomSelectConfigManager(str(tmp_path))
    config = manager.deserialize_device(
        {
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
                    "label": "Netflix",
                    "image_base64": "data:image/png;base64,AAAA",
                    "target_entity_id": "hass.main.media_player.tv",
                    "command_id": "media_player.select_source",
                    "params": {"source": "Netflix"},
                }
            ],
        }
    )

    assert config is not None
    assert config.label_style.bold is True
    assert config.options[0].label == "Netflix"
    assert config.options[0].params == {"source": "Netflix"}
