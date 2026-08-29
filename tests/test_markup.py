import base64

import pytest

from uc_intg_custom_select.config import LabelStyle, SelectOptionConfig
from uc_intg_custom_select.markup import (
    build_option_markup,
    normalize_base64_image,
    style_label,
)

PNG_1X1 = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"test-payload"
).decode()


def test_style_label_escapes_and_styles():
    value = style_label(
        'A < B & "C"',
        LabelStyle(bold=True, italic=True, underline=True, color="#ffffff", size=4),
    )
    assert "&lt;" in value
    assert "&amp;" in value
    assert "<b>" in value
    assert "<i>" in value
    assert "<u>" in value
    assert '<font color="#ffffff" size="4">' in value


def test_build_option_uses_qt_middle_alignment():
    option = SelectOptionConfig(
        label="Netflix",
        image_base64="data:image/png;base64,AAAA",
        target_entity_id="hass.main.media_player.tv",
        command_id="media_player.select_source",
    )
    value = build_option_markup(
        option,
        LabelStyle(bold=True),
        icon_size=96,
        image_alignment="middle",
        spacing=2,
    )
    assert 'align="middle"' in value
    assert 'width="96"' in value
    assert 'height="96"' in value
    assert "&nbsp;&nbsp;<b>Netflix</b>" in value


def test_normalize_base64_rejects_unknown_image():
    with pytest.raises(ValueError, match="Unsupported image format"):
        normalize_base64_image(base64.b64encode(b"not-an-image").decode())
