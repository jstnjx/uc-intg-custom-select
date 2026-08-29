"""Multi-screen setup flow for custom selects."""

import json
import logging
from typing import Any

from ucapi import IntegrationSetupError, RequestUserInput, SetupError
from ucapi_framework import BaseSetupFlow
from unfurled.api import CoreAPI
from unfurled.helpers.exceptions import AuthenticationError, ConnectionError, HTTPError

from .config import CustomSelectConfig, LabelStyle, SelectOptionConfig
from .const import (
    DEFAULT_ICON_SIZE,
    DEFAULT_SPACING,
    MAX_ICON_SIZE,
    MAX_OPTIONS,
    MAX_SPACING,
    MIN_ICON_SIZE,
)
from .markup import normalize_base64_image, validate_color
from .utils import entity_display_name, normalize_remote_url, slugify

_LOG = logging.getLogger(__name__)


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class CustomSelectSetupFlow(BaseSetupFlow[CustomSelectConfig]):
    """Create and edit one custom select per framework config entry."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._option_index = 0
        self._option_count = 0
        self._remote_entities: list[dict[str, Any]] = []

    def get_manual_entry_form(self) -> RequestUserInput:
        existing = self.selected_config_entry
        # When adding another Select, reuse the first configured Remote credentials
        # as defaults. They can still be changed, so one integration instance can
        # target multiple Remotes if desired without making the common case tedious.
        defaults = existing or next(iter(self.config.all()), None)

        return RequestUserInput(
            {"en": "Create Custom Select" if existing is None else "Edit Custom Select"},
            [
                {
                    "id": "info",
                    "label": {"en": "Custom Select"},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Connect to this Remote's Core API, define the Select, "
                                    "then configure each option and the existing entity command "
                                    "it should execute."
                                )
                            }
                        }
                    },
                },
                {
                    "id": "remote_url",
                    "label": {"en": "Remote address"},
                    "field": {
                        "text": {
                            "value": defaults.remote_url if defaults else ""
                        }
                    },
                },
                {
                    "id": "api_key",
                    "label": {"en": "Remote Core API key"},
                    "field": {
                        "password": {
                            "value": defaults.api_key if defaults else ""
                        }
                    },
                },
                {
                    "id": "name",
                    "label": {"en": "Select name"},
                    "field": {
                        "text": {
                            "value": existing.name if existing else "Custom Select"
                        }
                    },
                },
                {
                    "id": "identifier",
                    "label": {"en": "Select identifier"},
                    "field": {
                        "text": {
                            "value": existing.identifier if existing else ""
                        }
                    },
                },
                {
                    "id": "option_count",
                    "label": {"en": f"Number of options (1-{MAX_OPTIONS})"},
                    "field": {
                        "number": {
                            "value": len(existing.options) if existing else 2
                        }
                    },
                },
                {
                    "id": "icon_size",
                    "label": {
                        "en": f"Option icon size in px ({MIN_ICON_SIZE}-{MAX_ICON_SIZE})"
                    },
                    "field": {
                        "number": {
                            "value": existing.icon_size
                            if existing
                            else DEFAULT_ICON_SIZE
                        }
                    },
                },
                {
                    "id": "image_alignment",
                    "label": {"en": "Inline image alignment"},
                    "field": {
                        "dropdown": {
                            "value": existing.image_alignment
                            if existing
                            else "middle",
                            "items": [
                                {"id": "top", "label": {"en": "Top"}},
                                {"id": "middle", "label": {"en": "Middle"}},
                                {"id": "bottom", "label": {"en": "Bottom"}},
                            ],
                        }
                    },
                },
                {
                    "id": "spacing",
                    "label": {"en": f"Spaces between icon and name (0-{MAX_SPACING})"},
                    "field": {
                        "number": {
                            "value": existing.spacing if existing else DEFAULT_SPACING
                        }
                    },
                },
                {
                    "id": "label_bold",
                    "label": {"en": "Option names bold"},
                    "field": {
                        "checkbox": {
                            "value": existing.label_style.bold if existing else True
                        }
                    },
                },
                {
                    "id": "label_italic",
                    "label": {"en": "Option names italic"},
                    "field": {
                        "checkbox": {
                            "value": existing.label_style.italic if existing else False
                        }
                    },
                },
                {
                    "id": "label_underline",
                    "label": {"en": "Option names underlined"},
                    "field": {
                        "checkbox": {
                            "value": existing.label_style.underline
                            if existing
                            else False
                        }
                    },
                },
                {
                    "id": "label_color",
                    "label": {"en": "Option name color (optional)"},
                    "field": {
                        "text": {
                            "value": existing.label_style.color if existing else ""
                        }
                    },
                },
                {
                    "id": "label_size",
                    "label": {"en": "Option HTML font size (0 = Remote default, 1-7)"},
                    "field": {
                        "number": {
                            "value": existing.label_style.size if existing else 0
                        }
                    },
                },
            ],
        )

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> CustomSelectConfig | SetupError | RequestUserInput:
        try:
            remote_url = normalize_remote_url(str(input_values.get("remote_url", "")))
            api_key = str(input_values.get("api_key", "")).strip()
            name = str(input_values.get("name", "")).strip()
            identifier = str(input_values.get("identifier", "")).strip()
            identifier = slugify(identifier or name)

            if not api_key or not name:
                return SetupError(error_type=IntegrationSetupError.OTHER)

            option_count = int(input_values.get("option_count", 0))
            icon_size = int(input_values.get("icon_size", DEFAULT_ICON_SIZE))
            spacing = int(input_values.get("spacing", DEFAULT_SPACING))
            label_size = int(input_values.get("label_size", 0))
            image_alignment = str(
                input_values.get("image_alignment", "middle")
            ).strip().lower()
            color = validate_color(str(input_values.get("label_color", "")))

            if not 1 <= option_count <= MAX_OPTIONS:
                return SetupError(error_type=IntegrationSetupError.OTHER)
            if not MIN_ICON_SIZE <= icon_size <= MAX_ICON_SIZE:
                return SetupError(error_type=IntegrationSetupError.OTHER)
            if not 0 <= spacing <= MAX_SPACING:
                return SetupError(error_type=IntegrationSetupError.OTHER)
            if label_size not in range(0, 8):
                return SetupError(error_type=IntegrationSetupError.OTHER)
            if image_alignment not in {"top", "middle", "bottom"}:
                return SetupError(error_type=IntegrationSetupError.OTHER)

            if (
                self.selected_config_entry is None
                and self.config.contains(identifier)
            ):
                _LOG.warning("Select identifier already exists: %s", identifier)
                return SetupError(error_type=IntegrationSetupError.OTHER)

            self._remote_entities = await self._load_remote_entities(
                remote_url, api_key
            )

            existing = self.selected_config_entry
            old_options = list(existing.options) if existing else []
            self._pending_device_config = CustomSelectConfig(
                identifier=identifier,
                name=name,
                remote_url=remote_url,
                api_key=api_key,
                icon_size=icon_size,
                image_alignment=image_alignment,
                spacing=spacing,
                label_style=LabelStyle(
                    bold=_as_bool(input_values.get("label_bold", True)),
                    italic=_as_bool(input_values.get("label_italic", False)),
                    underline=_as_bool(input_values.get("label_underline", False)),
                    color=color,
                    size=label_size,
                ),
                options=old_options[:option_count],
            )
            self._option_count = option_count
            self._option_index = 0

            return self._build_option_screen(0)

        except AuthenticationError:
            return SetupError(error_type=IntegrationSetupError.AUTHORIZATION_ERROR)
        except (ConnectionError, TimeoutError):
            return SetupError(error_type=IntegrationSetupError.CONNECTION_REFUSED)
        except (HTTPError, ValueError, TypeError) as exc:
            _LOG.warning("Custom Select setup validation failed: %s", exc)
            return SetupError(error_type=IntegrationSetupError.OTHER)

    async def _load_remote_entities(
        self, remote_url: str, api_key: str
    ) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        async with CoreAPI(remote_url, api_key=api_key) as api:
            await api.get_system_info()
            for page in range(1, 101):
                batch = await api.get_entities(limit=100, page=page)
                if not batch:
                    break
                entities.extend(item for item in batch if isinstance(item, dict))
                if len(batch) < 100:
                    break

        entities.sort(key=lambda item: entity_display_name(item).casefold())
        return entities

    def _build_option_screen(self, index: int) -> RequestUserInput:
        if self._pending_device_config is None:
            raise RuntimeError("No pending Custom Select configuration")

        existing = (
            self._pending_device_config.options[index]
            if index < len(self._pending_device_config.options)
            else None
        )

        entity_items = []
        seen_ids: set[str] = set()
        for entity in self._remote_entities:
            entity_id = str(entity.get("entity_id") or entity.get("id") or "")
            if not entity_id or entity_id in seen_ids:
                continue
            seen_ids.add(entity_id)
            entity_items.append(
                {"id": entity_id, "label": {"en": entity_display_name(entity)}}
            )

        if existing and existing.target_entity_id not in seen_ids:
            entity_items.insert(
                0,
                {
                    "id": existing.target_entity_id,
                    "label": {
                        "en": f"{existing.target_entity_id} (currently unavailable)"
                    },
                },
            )

        if not entity_items:
            entity_items.append(
                {"id": "", "label": {"en": "No entities returned by Remote"}}
            )

        default_entity = (
            existing.target_entity_id if existing else entity_items[0]["id"]
        )
        params_value = (
            json.dumps(existing.params, ensure_ascii=False, separators=(",", ":"))
            if existing
            else "{}"
        )

        image_help = (
            "Paste raw Base64 or a data:image/...;base64,... URI. "
            "Leave blank to keep the existing image."
            if existing and existing.image_base64
            else "Paste raw Base64 or a data:image/...;base64,... URI."
        )

        return RequestUserInput(
            {"en": f"Option {index + 1} of {self._option_count}"},
            [
                {
                    "id": "option_info",
                    "label": {"en": "Option image and action"},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "The displayed option value is Qt StyledText: "
                                    "a Base64 inline image plus the styled option name. "
                                    "Selecting it executes the mapped Core entity command."
                                )
                            }
                        }
                    },
                },
                {
                    "id": "option_label",
                    "label": {"en": "Option name"},
                    "field": {
                        "text": {"value": existing.label if existing else ""}
                    },
                },
                {
                    "id": "image_help",
                    "label": {"en": "Base64 image"},
                    "field": {"label": {"value": {"en": image_help}}},
                },
                {
                    "id": "image_base64",
                    "label": {"en": "Base64 image data"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "target_entity_id",
                    "label": {"en": "Existing Remote entity"},
                    "field": {
                        "dropdown": {
                            "value": default_entity,
                            "items": entity_items,
                        }
                    },
                },
                {
                    "id": "command_id",
                    "label": {
                        "en": (
                            "Command ID (for example media_player.select_source, "
                            "activity.on, remote.send_cmd)"
                        )
                    },
                    "field": {
                        "text": {"value": existing.command_id if existing else ""}
                    },
                },
                {
                    "id": "command_params",
                    "label": {"en": "Command parameters as JSON object"},
                    "field": {"text": {"value": params_value}},
                },
            ],
        )

    async def handle_additional_configuration_response(
        self, msg
    ) -> RequestUserInput | SetupError | CustomSelectConfig | None:
        if self._pending_device_config is None:
            return SetupError(error_type=IntegrationSetupError.OTHER)

        values = msg.input_values
        label = str(values.get("option_label", "")).strip()
        target_entity_id = str(values.get("target_entity_id", "")).strip()
        command_id = str(values.get("command_id", "")).strip()

        if not label or not target_entity_id or not command_id:
            return SetupError(error_type=IntegrationSetupError.OTHER)

        try:
            params_raw = str(values.get("command_params", "{}")).strip() or "{}"
            params = json.loads(params_raw)
            if not isinstance(params, dict):
                raise ValueError("Command parameters must be a JSON object")

            image_input = str(values.get("image_base64", "")).strip()
            existing = (
                self._pending_device_config.options[self._option_index]
                if self._option_index < len(self._pending_device_config.options)
                else None
            )
            if image_input:
                image_base64 = normalize_base64_image(image_input)
            elif existing:
                image_base64 = existing.image_base64
            else:
                image_base64 = ""

            option = SelectOptionConfig(
                label=label,
                image_base64=image_base64,
                target_entity_id=target_entity_id,
                command_id=command_id,
                params=params,
            )

            if self._option_index < len(self._pending_device_config.options):
                self._pending_device_config.options[self._option_index] = option
            else:
                self._pending_device_config.options.append(option)

            self._option_index += 1
            if self._option_index < self._option_count:
                return self._build_option_screen(self._option_index)

            self._pending_device_config.options = self._pending_device_config.options[
                : self._option_count
            ]
            return None

        except (json.JSONDecodeError, ValueError) as exc:
            _LOG.warning("Invalid option configuration: %s", exc)
            return SetupError(error_type=IntegrationSetupError.OTHER)

    async def _build_configuration_mode_screen(self) -> RequestUserInput:
        configured = []
        for item in self.config.all():
            configured.append(
                {"id": item.identifier, "label": {"en": item.name}}
            )

        if not configured:
            configured = [{"id": "", "label": {"en": "---"}}]

        actions = [{"id": "add", "label": {"en": "Create another Select"}}]
        if any(self.config.all()):
            actions.extend(
                [
                    {"id": "update", "label": {"en": "Edit selected Select"}},
                    {"id": "remove", "label": {"en": "Remove selected Select"}},
                    {"id": "reset", "label": {"en": "Reset all Selects"}},
                    {"id": "backup", "label": {"en": "Backup configuration"}},
                    {"id": "restore", "label": {"en": "Restore configuration"}},
                ]
            )
        else:
            actions.append(
                {"id": "restore", "label": {"en": "Restore configuration"}}
            )

        return RequestUserInput(
            {"en": "Custom Select configuration"},
            [
                {
                    "id": "choice",
                    "label": {"en": "Configured Selects"},
                    "field": {
                        "dropdown": {
                            "value": configured[0]["id"],
                            "items": configured,
                        }
                    },
                },
                {
                    "id": "action",
                    "label": {"en": "Action"},
                    "field": {
                        "dropdown": {
                            "value": actions[0]["id"],
                            "items": actions,
                        }
                    },
                },
            ],
        )
