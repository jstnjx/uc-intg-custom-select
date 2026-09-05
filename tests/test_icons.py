"""Tests for native UC and uploaded resource icon handling."""

import base64

import pytest

from uc_intg_custom_select.icons import (
    build_uc_icon_data_uri,
    normalize_custom_icon_ref,
    normalize_uc_icon_ref,
    option_icon_source,
)


def test_legacy_base64_is_detected_without_icon_reference() -> None:
    assert option_icon_source("", "data:image/png;base64,AAAA") == "base64"


def test_native_and_resource_sources_are_detected() -> None:
    assert option_icon_source("uc:house", "") == "uc"
    assert option_icon_source("custom:my-icon.png", "cached") == "resource"
    assert option_icon_source("", "") == "none"


def test_icon_reference_normalization() -> None:
    assert normalize_uc_icon_ref(" House ") == "uc:house"
    assert normalize_uc_icon_ref("UC:Lightbulb-On") == "uc:lightbulb-on"
    assert normalize_custom_icon_ref("custom:My Icon.png") == "custom:My Icon.png"


@pytest.mark.parametrize("value", ["", "../icon.png", "folder/icon.png"])
def test_custom_resource_rejects_invalid_path(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_custom_icon_ref(value)


def test_uc_icon_is_rendered_as_font_awesome_svg_data_uri() -> None:
    uri = build_uc_icon_data_uri("\ue900")
    assert uri.startswith("data:image/svg+xml;base64,")

    svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")
    assert 'font-family="Font Awesome 6 Pro"' in svg
    assert "&#xE900;" in svg
