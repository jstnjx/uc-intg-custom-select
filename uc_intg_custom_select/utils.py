"""Small integration helpers."""

import re
from urllib.parse import urlsplit, urlunsplit


def slugify(value: str) -> str:
    """Create a stable UC entity-safe identifier fragment."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "custom_select"


def normalize_remote_url(value: str) -> str:
    """Normalize a Remote address to the Core REST API base URL."""
    value = value.strip()
    if not value:
        raise ValueError("Remote address is required")

    if "://" not in value:
        value = "http://" + value

    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("Remote address must be a valid HTTP(S) URL or hostname")

    path = parts.path.rstrip("/")
    if not path:
        path = "/api"
    elif path != "/api" and not path.endswith("/api"):
        path = path + "/api"

    return urlunsplit((parts.scheme, parts.netloc, path + "/", "", ""))


def entity_display_name(entity: dict) -> str:
    """Create a readable dropdown label from a Core entity payload."""
    entity_id = str(entity.get("entity_id") or entity.get("id") or "")
    name = entity.get("name")

    if isinstance(name, dict):
        for key in ("en", "en_US", "de", "de_DE"):
            candidate = name.get(key)
            if candidate:
                name = candidate
                break
        else:
            name = next((v for v in name.values() if v), "")
    elif name is None:
        name = ""

    name = str(name).strip()
    return f"{name} — {entity_id}" if name else entity_id
