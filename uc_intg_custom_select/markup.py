"""Build and validate the Qt StyledText used as select option values."""

import base64
import binascii
import html
import re

from .config import LabelStyle, SelectOptionConfig
from .const import MAX_IMAGE_BYTES

_DATA_URI_RE = re.compile(
    r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$",
    re.IGNORECASE | re.DOTALL,
)
_COLOR_RE = re.compile(r"^(?:#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?|[a-zA-Z]+)$")


def _detect_image_mime(data: bytes) -> str:
    """Detect common inline image formats from magic bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    stripped = data.lstrip()
    if stripped.startswith(b"<svg") or (
        stripped.startswith(b"<?xml") and b"<svg" in stripped[:1024]
    ):
        return "image/svg+xml"

    raise ValueError("Unsupported image format; use PNG, JPEG, GIF, WebP or SVG")


def normalize_base64_image(value: str) -> str:
    """Return a canonical image data URI from raw Base64 or a data URI."""
    value = value.strip()
    if not value:
        return ""

    match = _DATA_URI_RE.match(value)
    declared_mime = None
    payload = value
    if match:
        declared_mime = match.group(1).lower()
        payload = match.group(2)

    payload = "".join(payload.split())
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Image is not valid Base64") from exc

    if not decoded:
        raise ValueError("Image payload is empty")
    if len(decoded) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image is too large ({len(decoded)} bytes); maximum is {MAX_IMAGE_BYTES} bytes"
        )

    detected_mime = _detect_image_mime(decoded)
    if declared_mime and declared_mime != detected_mime:
        # SVG is sometimes declared as text-ish by image exporters, but only image/*
        # is allowed by the data URI parser above. Keep strict validation here.
        raise ValueError(
            f"Declared image type {declared_mime} does not match {detected_mime}"
        )

    canonical = base64.b64encode(decoded).decode("ascii")
    return f"data:{detected_mime};base64,{canonical}"


def validate_color(value: str) -> str:
    """Validate a Qt/HTML color name or #RRGGBB/#RRGGBBAA literal."""
    value = value.strip()
    if not value:
        return ""
    if not _COLOR_RE.fullmatch(value):
        raise ValueError("Color must be a name or #RRGGBB/#RRGGBBAA")
    return value


def style_label(label: str, style: LabelStyle) -> str:
    """Escape and wrap an option label with Qt StyledText-compatible tags."""
    value = html.escape(label, quote=True)

    if style.bold:
        value = f"<b>{value}</b>"
    if style.italic:
        value = f"<i>{value}</i>"
    if style.underline:
        value = f"<u>{value}</u>"

    font_attributes: list[str] = []
    if style.color:
        font_attributes.append(f'color="{html.escape(style.color, quote=True)}"')
    if style.size:
        font_attributes.append(f'size="{style.size}"')
    if font_attributes:
        value = f"<font {' '.join(font_attributes)}>{value}</font>"

    return value


def build_option_markup(
    option: SelectOptionConfig,
    style: LabelStyle,
    icon_size: int,
    image_alignment: str,
    spacing: int,
) -> str:
    """Create the exact select option string rendered by stock remote-ui."""
    label = style_label(option.label, style)
    gap = "&nbsp;" * spacing

    if not option.image_base64:
        return label

    return (
        f'<img src="{option.image_base64}" align="{image_alignment}" '
        f'width="{icon_size}" height="{icon_size}">{gap}{label}'
    )
