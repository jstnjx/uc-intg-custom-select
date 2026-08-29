"""Timeout-safe setup flow extensions for Custom Select."""

import asyncio
import copy
import json
from typing import Any

from ucapi import IntegrationSetupError, RequestUserInput, SetupError

from .config import LabelStyle, SelectOptionConfig
from .const import (
    DEFAULT_ICON_SIZE,
    DEFAULT_SPACING,
    MAX_ICON_SIZE,
    MAX_OPTIONS,
    MAX_SPACING,
    MIN_ICON_SIZE,
)
from .markup import normalize_base64_image, validate_color
from .setup import CustomSelectSetupFlow


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class TimeoutSafeCustomSelectSetupFlow(CustomSelectSetupFlow):
    """Setup flow that never requires editing every option in one reconfigure run."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._quick_operation = ""

    def get_manual_entry_form(self) -> RequestUserInput:
        """Default new Selects to one option to avoid long initial setup sessions."""
        form = super().get_manual_entry_form()
        if self.selected_config_entry is None:
            for setting in form.settings:
                if setting.get("id") == "option_count":
                    setting["label"] = {
                        "en": (
                            f"Options to configure now (1-{MAX_OPTIONS}; add more later "
                            "from Reconfigure)"
                        )
                    }
                    setting["field"]["number"]["value"] = 1
                    break
        return form

    async def _build_configuration_mode_screen(self) -> RequestUserInput:
        configured_entries = list(self.config.all())
        configured = [
            {"id": item.identifier, "label": {"en": item.name}}
            for item in configured_entries
        ]
        if not configured:
            configured = [{"id": "", "label": {"en": "---"}}]

        actions = [{"id": "add", "label": {"en": "Create another Select"}}]
        if configured_entries:
            actions.extend(
                [
                    {
                        "id": "edit_settings",
                        "label": {"en": "Edit selected Select styling/settings"},
                    },
                    {
                        "id": "add_option",
                        "label": {"en": "Add one option to selected Select"},
                    },
                    {
                        "id": "edit_option",
                        "label": {"en": "Edit one option on selected Select"},
                    },
                    {
                        "id": "remove_option",
                        "label": {"en": "Remove one option from selected Select"},
                    },
                    {"id": "remove", "label": {"en": "Remove selected Select"}},
                    {"id": "reset", "label": {"en": "Reset all Selects"}},
                    {"id": "backup", "label": {"en": "Backup configuration"}},
                    {"id": "restore", "label": {"en": "Restore configuration"}},
                ]
            )
        else:
            actions.append({"id": "restore", "label": {"en": "Restore configuration"}})

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

    async def _handle_configuration_mode(self, msg):
        action = str(msg.input_values.get("action", ""))
        if action not in {
            "edit_settings",
            "add_option",
            "edit_option",
            "remove_option",
        }:
            self._quick_operation = ""
            return await super()._handle_configuration_mode(msg)

        # Match the framework's Web Configurator response workaround.
        await asyncio.sleep(1)

        choice = str(msg.input_values.get("choice", ""))
        existing = self.config.get(choice)
        if existing is None:
            return SetupError(error_type=IntegrationSetupError.OTHER)

        self._selected_config_id = choice
        self._pending_device_config = copy.deepcopy(existing)

        if action == "edit_settings":
            self._quick_operation = "settings"
            return self._build_settings_screen()

        if action == "add_option":
            if len(existing.options) >= MAX_OPTIONS:
                return SetupError(error_type=IntegrationSetupError.OTHER)
            self._remote_entities = await self._load_remote_entities(
                existing.remote_url, existing.api_key
            )
            self._option_index = len(existing.options)
            self._option_count = len(existing.options) + 1
            self._quick_operation = "save_single_option"
            return self._build_option_screen(self._option_index)

        if not existing.options:
            return SetupError(error_type=IntegrationSetupError.OTHER)

        if action == "edit_option":
            self._remote_entities = await self._load_remote_entities(
                existing.remote_url, existing.api_key
            )
            self._option_count = len(existing.options)
            self._quick_operation = "choose_edit_option"
            return self._build_option_choice_screen("Edit option")

        self._quick_operation = "choose_remove_option"
        return self._build_option_choice_screen("Remove option")

    def _build_option_choice_screen(self, title: str) -> RequestUserInput:
        if self._pending_device_config is None:
            raise RuntimeError("No pending Custom Select configuration")

        items = [
            {"id": str(index), "label": {"en": option.label}}
            for index, option in enumerate(self._pending_device_config.options)
        ]
        return RequestUserInput(
            {"en": title},
            [
                {
                    "id": "option_index",
                    "label": {"en": "Option"},
                    "field": {
                        "dropdown": {
                            "value": items[0]["id"],
                            "items": items,
                        }
                    },
                }
            ],
        )

    def _build_settings_screen(self) -> RequestUserInput:
        if self._pending_device_config is None:
            raise RuntimeError("No pending Custom Select configuration")
        config = self._pending_device_config
        return RequestUserInput(
            {"en": "Edit Select styling/settings"},
            [
                {
                    "id": "name",
                    "label": {"en": "Select name"},
                    "field": {"text": {"value": config.name}},
                },
                {
                    "id": "icon_size",
                    "label": {
                        "en": f"Option icon size in px ({MIN_ICON_SIZE}-{MAX_ICON_SIZE})"
                    },
                    "field": {"number": {"value": config.icon_size}},
                },
                {
                    "id": "image_alignment",
                    "label": {"en": "Inline image alignment"},
                    "field": {
                        "dropdown": {
                            "value": config.image_alignment,
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
                    "field": {"number": {"value": config.spacing}},
                },
                {
                    "id": "label_bold",
                    "label": {"en": "Option names bold"},
                    "field": {"checkbox": {"value": config.label_style.bold}},
                },
                {
                    "id": "label_italic",
                    "label": {"en": "Option names italic"},
                    "field": {"checkbox": {"value": config.label_style.italic}},
                },
                {
                    "id": "label_underline",
                    "label": {"en": "Option names underlined"},
                    "field": {"checkbox": {"value": config.label_style.underline}},
                },
                {
                    "id": "label_color",
                    "label": {"en": "Option name color (optional)"},
                    "field": {"text": {"value": config.label_style.color}},
                },
                {
                    "id": "label_size",
                    "label": {"en": "Option HTML font size (0 = Remote default, 1-7)"},
                    "field": {"number": {"value": config.label_style.size}},
                },
            ],
        )

    async def handle_additional_configuration_response(
        self, msg
    ) -> RequestUserInput | SetupError | None:
        if self._pending_device_config is None:
            return SetupError(error_type=IntegrationSetupError.OTHER)

        if self._quick_operation == "settings":
            return self._save_settings(msg.input_values)

        if self._quick_operation in {"choose_edit_option", "choose_remove_option"}:
            try:
                index = int(msg.input_values.get("option_index", "-1"))
            except (TypeError, ValueError):
                return SetupError(error_type=IntegrationSetupError.OTHER)

            if not 0 <= index < len(self._pending_device_config.options):
                return SetupError(error_type=IntegrationSetupError.OTHER)

            if self._quick_operation == "choose_remove_option":
                del self._pending_device_config.options[index]
                self._quick_operation = ""
                return None

            self._option_index = index
            self._quick_operation = "save_single_option"
            return self._build_option_screen(index)

        if self._quick_operation == "save_single_option":
            result = self._save_single_option(msg.input_values)
            if not isinstance(result, SetupError):
                self._quick_operation = ""
            return result

        return await super().handle_additional_configuration_response(msg)

    def _save_single_option(self, values: dict[str, Any]) -> SetupError | None:
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

            existing = (
                self._pending_device_config.options[self._option_index]
                if self._option_index < len(self._pending_device_config.options)
                else None
            )
            image_input = str(values.get("image_base64", "")).strip()
            if image_input:
                image_base64 = normalize_base64_image(image_input)
            elif existing is not None:
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
            if existing is not None:
                self._pending_device_config.options[self._option_index] = option
            else:
                self._pending_device_config.options.append(option)
            return None
        except (json.JSONDecodeError, ValueError):
            return SetupError(error_type=IntegrationSetupError.OTHER)

    def _save_settings(self, values: dict[str, Any]) -> SetupError | None:
        try:
            name = str(values.get("name", "")).strip()
            icon_size = int(values.get("icon_size", DEFAULT_ICON_SIZE))
            spacing = int(values.get("spacing", DEFAULT_SPACING))
            label_size = int(values.get("label_size", 0))
            image_alignment = str(values.get("image_alignment", "middle")).strip().lower()
            color = validate_color(str(values.get("label_color", "")))

            if not name:
                raise ValueError("Select name is required")
            if not MIN_ICON_SIZE <= icon_size <= MAX_ICON_SIZE:
                raise ValueError("Invalid icon size")
            if not 0 <= spacing <= MAX_SPACING:
                raise ValueError("Invalid spacing")
            if label_size not in range(0, 8):
                raise ValueError("Invalid label size")
            if image_alignment not in {"top", "middle", "bottom"}:
                raise ValueError("Invalid image alignment")

            self._pending_device_config.name = name
            self._pending_device_config.icon_size = icon_size
            self._pending_device_config.image_alignment = image_alignment
            self._pending_device_config.spacing = spacing
            self._pending_device_config.label_style = LabelStyle(
                bold=_bool(values.get("label_bold", True)),
                italic=_bool(values.get("label_italic", False)),
                underline=_bool(values.get("label_underline", False)),
                color=color,
                size=label_size,
            )
            self._quick_operation = ""
            return None
        except (TypeError, ValueError):
            return SetupError(error_type=IntegrationSetupError.OTHER)
