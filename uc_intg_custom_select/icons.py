"""Resolve Remote icon references into StyledText-compatible inline images."""

from __future__ import annotations

import base64
import html
import re
from typing import Any
from urllib.parse import quote

from unfurled.api import CoreAPI

from .markup import normalize_base64_image

UC_ICON_PREFIX = "uc:"
CUSTOM_ICON_PREFIX = "custom:"
_HEX_CODEPOINT_RE = re.compile(r"^[0-9a-fA-F]{1,6}$")


def option_icon_source(icon: str, image_base64: str) -> str:
    """Return the configured icon source identifier for an option."""
    value = icon.strip().lower()
    if value.startswith(UC_ICON_PREFIX):
        return "uc"
    if value.startswith(CUSTOM_ICON_PREFIX):
        return "resource"
    if image_base64.strip():
        return "base64"
    return "none"


def normalize_uc_icon_ref(value: str) -> str:
    """Normalize a built-in UC icon identifier to ``uc:<name>``."""
    value = value.strip()
    if value.lower().startswith(UC_ICON_PREFIX):
        value = value[len(UC_ICON_PREFIX) :]
    value = value.strip().lower()
    if not value or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ValueError("UC icon must be a valid identifier such as uc:house")
    return f"{UC_ICON_PREFIX}{value}"


def normalize_custom_icon_ref(value: str) -> str:
    """Normalize a user-uploaded Icon resource to ``custom:<resource-id>``."""
    value = value.strip()
    if value.lower().startswith(CUSTOM_ICON_PREFIX):
        value = value[len(CUSTOM_ICON_PREFIX) :]
    value = value.strip()
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("Custom icon must be an uploaded Icon resource identifier")
    return f"{CUSTOM_ICON_PREFIX}{value}"


def _mapping_codepoint(value: Any) -> int:
    """Convert Core's native icon mapping value to a Unicode codepoint."""
    text = str(value).strip()
    if len(text) == 1:
        return ord(text)

    lowered = text.lower()
    if lowered.startswith("&#x") and lowered.endswith(";"):
        text = text[3:-1]
    elif lowered.startswith("\\u") or lowered.startswith("0x"):
        text = text[2:]
    elif lowered.startswith("u") and len(text) > 1:
        text = text[1:]

    if not _HEX_CODEPOINT_RE.fullmatch(text):
        raise ValueError(f"Invalid UC icon mapping value: {value!r}")

    codepoint = int(text, 16)
    if codepoint > 0x10FFFF:
        raise ValueError(f"Invalid Unicode codepoint: {codepoint:#x}")
    return codepoint


def build_uc_icon_data_uri(mapping_value: Any) -> str:
    """Render a UC Font Awesome glyph as an inline SVG data URI.

    Qt StyledText cannot select a font family for an inline character, while the
    stock Remote UI renders UC icons with the globally registered
    ``Font Awesome 6 Pro`` font. Wrapping the mapped glyph in a tiny SVG lets the
    existing StyledText ``<img>`` path use the same native font without bundling
    firmware icon tables or font files in this integration.
    """
    codepoint = _mapping_codepoint(mapping_value)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="90" height="90" '
        'viewBox="0 0 90 90">'
        '<text x="45" y="69" text-anchor="middle" '
        'font-family="Font Awesome 6 Pro" font-size="72" fill="#f5f5f5">'
        f"&#x{codepoint:X};"
        "</text></svg>"
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return normalize_base64_image(encoded)


async def get_uc_icon_mapping(api: CoreAPI) -> dict[str, Any]:
    """Fetch the built-in icon mapping from the connected Remote."""
    payload = await api.request("GET", "cfg/device/icon_mapping")
    if not isinstance(payload, dict):
        raise ValueError("Remote returned an invalid UC icon mapping")
    return {
        str(name).strip().lower(): value
        for name, value in payload.items()
        if str(name).strip()
    }


async def list_custom_icon_resources(api: CoreAPI) -> list[str]:
    """List user-uploaded resources of Core type ``Icon``."""
    resource_ids: set[str] = set()
    for page in range(1, 101):
        payload = await api.request(
            "GET", "resources/Icon", params={"limit": 50, "page": page}
        )
        if not isinstance(payload, list):
            raise ValueError("Remote returned an invalid Icon resource list")
        for item in payload:
            if not isinstance(item, dict):
                continue
            resource_id = str(item.get("id", "")).strip()
            if resource_id:
                resource_ids.add(resource_id)
        if len(payload) < 50:
            break
    return sorted(resource_ids, key=str.casefold)


async def resolve_icon_reference(
    api: CoreAPI,
    icon_ref: str,
    *,
    uc_mapping: dict[str, Any] | None = None,
) -> str:
    """Resolve ``uc:`` or ``custom:`` into a canonical inline image data URI."""
    source = option_icon_source(icon_ref, "")
    if source == "uc":
        normalized = normalize_uc_icon_ref(icon_ref)
        mapping = uc_mapping if uc_mapping is not None else await get_uc_icon_mapping(api)
        name = normalized[len(UC_ICON_PREFIX) :]
        if name not in mapping:
            raise ValueError(f"Unknown built-in UC icon: {normalized}")
        return build_uc_icon_data_uri(mapping[name])

    if source == "resource":
        normalized = normalize_custom_icon_ref(icon_ref)
        resource_id = normalized[len(CUSTOM_ICON_PREFIX) :]
        payload = await api.request(
            "GET",
            f"resources/Icon/{quote(resource_id, safe='')}",
            headers={"Accept": "*/*"},
            response_type="bytes",
        )
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            raise ValueError(f"Icon resource is empty: {resource_id}")
        encoded = base64.b64encode(bytes(payload)).decode("ascii")
        return normalize_base64_image(encoded)

    raise ValueError(f"Unsupported icon reference: {html.escape(icon_ref)}")
