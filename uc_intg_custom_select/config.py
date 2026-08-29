"""Persistent configuration models."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ucapi_framework import BaseConfigManager

_LOG = logging.getLogger(__name__)


@dataclass
class LabelStyle:
    """Qt StyledText-compatible option label styling."""

    bold: bool = True
    italic: bool = False
    underline: bool = False
    color: str = ""
    size: int = 0


@dataclass
class SelectOptionConfig:
    """One displayed select option and the command it triggers."""

    label: str
    image_base64: str
    target_entity_id: str
    command_id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomSelectConfig:
    """Configuration for one custom select entity."""

    identifier: str
    name: str
    remote_url: str
    api_key: str
    icon_size: int = 96
    image_alignment: str = "middle"
    spacing: int = 2
    label_style: LabelStyle = field(default_factory=LabelStyle)
    options: list[SelectOptionConfig] = field(default_factory=list)


class CustomSelectConfigManager(BaseConfigManager[CustomSelectConfig]):
    """Config manager with explicit nested dataclass deserialization."""

    def deserialize_device(self, data: dict) -> CustomSelectConfig | None:
        try:
            style_data = data.get("label_style") or {}
            style = LabelStyle(
                bold=bool(style_data.get("bold", True)),
                italic=bool(style_data.get("italic", False)),
                underline=bool(style_data.get("underline", False)),
                color=str(style_data.get("color", "")),
                size=int(style_data.get("size", 0)),
            )

            options = []
            for item in data.get("options", []):
                if not isinstance(item, dict):
                    continue
                params = item.get("params")
                if not isinstance(params, dict):
                    params = {}
                options.append(
                    SelectOptionConfig(
                        label=str(item.get("label", "")),
                        image_base64=str(item.get("image_base64", "")),
                        target_entity_id=str(item.get("target_entity_id", "")),
                        command_id=str(item.get("command_id", "")),
                        params=params,
                    )
                )

            return CustomSelectConfig(
                identifier=str(data["identifier"]),
                name=str(data["name"]),
                remote_url=str(data["remote_url"]),
                api_key=str(data["api_key"]),
                icon_size=int(data.get("icon_size", 96)),
                image_alignment=str(data.get("image_alignment", "middle")),
                spacing=int(data.get("spacing", 2)),
                label_style=style,
                options=options,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def restore_from_backup_json(self, backup_json: str) -> bool:
        """Restore config and rebuild runtime devices from the restored entries.

        ucapi-framework's generic restore callback adds restored configs without first
        removing already-running device instances. BaseIntegrationDriver then reuses an
        instance with the same identifier, which can leave an edited backup persisted on
        disk while the Select continues serving its pre-restore options in memory.

        Validate and persist the complete replacement first, then clear runtime devices
        through the framework remove callback and add each restored config again.
        """
        try:
            data = json.loads(backup_json)
            if not isinstance(data, list):
                _LOG.error("Invalid backup format: expected list")
                return False

            restored: list[CustomSelectConfig] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                device = self.deserialize_device(item)
                if device is not None:
                    restored.append(device)

            if not restored:
                _LOG.error("No valid Custom Select entries found in backup")
                return False

            previous = self._config
            self._config = restored
            if not self.store():
                self._config = previous
                return False

            if self._remove_handler is not None:
                self._remove_handler(None)
            if self._add_handler is not None:
                for device in restored:
                    self._add_handler(device)

            _LOG.info(
                "Restored %d Custom Select configuration entr%s and rebuilt runtime state",
                len(restored),
                "y" if len(restored) == 1 else "ies",
            )
            return True
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            _LOG.error("Failed to restore Custom Select backup: %s", exc)
            return False
