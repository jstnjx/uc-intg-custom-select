"""Icon-aware setup layer for Custom Select."""

from __future__ import annotations

import logging
from typing import Any

from ucapi import IntegrationSetupError, RequestUserInput, SetupError
from unfurled.api import CoreAPI

from .config import SelectOptionConfig
from .icons import (
    CUSTOM_ICON_PREFIX,
    UC_ICON_PREFIX,
    build_uc_icon_data_uri,
    get_uc_icon_mapping,
    list_custom_icon_resources,
    normalize_custom_icon_ref,
    normalize_uc_icon_ref,
    option_icon_source,
    resolve_icon_reference,
)
from .setup_fast import TimeoutSafeCustomSelectSetupFlow

_LOG = logging.getLogger(__name__)


class IconAwareCustomSelectSetupFlow(TimeoutSafeCustomSelectSetupFlow):
    """Extend the existing setup flow with native and uploaded icon sources."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._uc_icon_mapping: dict[str, Any] = {}
        self._custom_icon_resources: list[str] = []

    async def _load_remote_entities(
        self, remote_url: str, api_key: str
    ) -> list[dict[str, Any]]:
        """Load entities plus icon metadata whenever an option editor is opened."""
        entities = await super()._load_remote_entities(remote_url, api_key)
        await self._load_remote_icon_sources(remote_url, api_key)
        return entities

    async def _load_remote_icon_sources(self, remote_url: str, api_key: str) -> None:
        """Best-effort discovery of native icons and user-uploaded Icon resources."""
        self._uc_icon_mapping = {}
        self._custom_icon_resources = []
        async with CoreAPI(remote_url, api_key=api_key) as api:
            try:
                self._uc_icon_mapping = await get_uc_icon_mapping(api)
            except Exception as exc:  # noqa: BLE001 - Base64 remains usable
                _LOG.warning("Could not load built-in UC icon mapping: %s", exc)

            try:
                self._custom_icon_resources = await list_custom_icon_resources(api)
            except Exception as exc:  # noqa: BLE001 - Base64 remains usable
                _LOG.warning("Could not load uploaded Icon resources: %s", exc)

    def _build_option_screen(self, index: int) -> RequestUserInput:
        """Add an icon-source selector to the existing option editor."""
        form = super()._build_option_screen(index)
        if self._pending_device_config is None:
            return form

        existing = (
            self._pending_device_config.options[index]
            if index < len(self._pending_device_config.options)
            else None
        )
        source = (
            option_icon_source(existing.icon, existing.image_base64)
            if existing is not None
            else "none"
        )

        uc_value = existing.icon if existing and source == "uc" else ""
        existing_resource = (
            existing.icon[len(CUSTOM_ICON_PREFIX) :]
            if existing and source == "resource"
            else ""
        )

        resource_ids = list(self._custom_icon_resources)
        if existing_resource and existing_resource not in resource_ids:
            resource_ids.insert(0, existing_resource)
        resource_items = [
            {"id": resource_id, "label": {"en": resource_id}}
            for resource_id in resource_ids
        ]
        if not resource_items:
            resource_items = [
                {"id": "", "label": {"en": "No uploaded Icon resources found"}}
            ]
        resource_value = existing_resource or resource_items[0]["id"]

        icon_settings = [
            {
                "id": "icon_source",
                "label": {"en": "Option icon source"},
                "field": {
                    "dropdown": {
                        "value": source,
                        "items": [
                            {"id": "none", "label": {"en": "No icon"}},
                            {"id": "uc", "label": {"en": "Built-in UC icon"}},
                            {
                                "id": "resource",
                                "label": {"en": "Uploaded Icon resource"},
                            },
                            {
                                "id": "base64",
                                "label": {"en": "Base64 / data URI"},
                            },
                        ],
                    }
                },
            },
            {
                "id": "uc_icon",
                "label": {"en": "Built-in UC icon identifier"},
                "field": {"text": {"value": uc_value}},
            },
            {
                "id": "resource_icon",
                "label": {"en": "Uploaded Icon resource"},
                "field": {
                    "dropdown": {
                        "value": resource_value,
                        "items": resource_items,
                    }
                },
            },
        ]

        rebuilt: list[dict[str, Any]] = []
        for setting in form.settings:
            setting_id = setting.get("id")
            if setting_id == "option_info":
                setting["field"]["label"]["value"]["en"] = (
                    "Choose a built-in uc: icon, a user-uploaded Icon resource, "
                    "Base64/data URI, or no icon. Native/resource icons are resolved "
                    "from this Remote and cached as StyledText-compatible inline images."
                )
            if setting_id == "image_help":
                rebuilt.extend(icon_settings)
                setting["label"] = {"en": "Base64 image"}
                setting["field"]["label"]["value"]["en"] = (
                    "Used only when the icon source is Base64 / data URI. Paste raw "
                    "Base64 or data:image/...;base64,...; leave blank to keep an "
                    "existing Base64 image. Built-in examples use identifiers such as "
                    "uc:house."
                )
            rebuilt.append(setting)

        form.settings[:] = rebuilt
        return form

    def _build_option_retry_screen(
        self,
        error: str,
        values: dict[str, Any],
    ) -> RequestUserInput:
        """Reopen the option editor after validation without aborting setup."""
        form = self._build_option_screen(self._option_index)
        form.settings.insert(
            0,
            {
                "id": "option_error",
                "label": {"en": "Could not save option"},
                "field": {
                    "label": {
                        "value": {
                            "en": error,
                        }
                    }
                },
            },
        )

        # Preserve the submitted values so a single validation error does not force
        # the user to re-enter the complete option. Label-only settings are ignored.
        for setting in form.settings:
            setting_id = str(setting.get("id", ""))
            if setting_id not in values:
                continue
            field = setting.get("field")
            if not isinstance(field, dict):
                continue
            for field_type in ("text", "dropdown", "number", "checkbox", "password"):
                field_config = field.get(field_type)
                if isinstance(field_config, dict) and "value" in field_config:
                    field_config["value"] = values[setting_id]
                    break

        return form

    async def _resolve_selected_icon(
        self,
        values: dict[str, Any],
        existing: SelectOptionConfig | None,
    ) -> tuple[str, str, str]:
        """Return ``(source, icon_ref, cached_data_uri)`` for the submitted option."""
        source = str(values.get("icon_source", "none")).strip().lower()
        current_source = (
            option_icon_source(existing.icon, existing.image_base64)
            if existing is not None
            else "none"
        )

        if source == "none":
            return source, "", ""

        if source == "base64":
            raw = str(values.get("image_base64", "")).strip()
            if raw:
                # The existing setup flow performs the canonical Base64 validation.
                return source, "", raw
            if existing is not None and current_source == "base64" and existing.image_base64:
                return source, "", ""
            raise ValueError("Base64 image data is required when switching icon source")

        if source == "uc":
            raw = str(values.get("uc_icon", "")).strip()
            if not raw and existing is not None and current_source == "uc":
                raw = existing.icon
            icon_ref = normalize_uc_icon_ref(raw)
            icon_name = icon_ref[len(UC_ICON_PREFIX) :]
            mapping_value = self._uc_icon_mapping.get(icon_name)
            if mapping_value is not None:
                return source, icon_ref, build_uc_icon_data_uri(mapping_value)
            if existing is not None and existing.icon == icon_ref and existing.image_base64:
                _LOG.warning(
                    "Built-in icon %s is no longer in the Remote mapping; keeping cache",
                    icon_ref,
                )
                return source, icon_ref, existing.image_base64
            raise ValueError(f"Unknown built-in UC icon: {icon_ref}")

        if source == "resource":
            raw = str(values.get("resource_icon", "")).strip()
            if not raw and existing is not None and current_source == "resource":
                raw = existing.icon
            icon_ref = normalize_custom_icon_ref(raw)
            if self._pending_device_config is None:
                raise ValueError("No pending Custom Select configuration")

            try:
                async with CoreAPI(
                    self._pending_device_config.remote_url,
                    api_key=self._pending_device_config.api_key,
                ) as api:
                    image = await resolve_icon_reference(api, icon_ref)
                return source, icon_ref, image
            except Exception:  # noqa: BLE001 - preserve a known-good cached resource
                if (
                    existing is not None
                    and existing.icon == icon_ref
                    and existing.image_base64
                ):
                    _LOG.warning(
                        "Uploaded icon %s could not be refreshed; keeping cached image",
                        icon_ref,
                    )
                    return source, icon_ref, existing.image_base64
                raise

        raise ValueError(f"Unsupported icon source: {source}")

    async def handle_additional_configuration_response(
        self, msg
    ) -> RequestUserInput | SetupError | None:
        """Resolve native/resource selections before delegating to existing save logic."""
        values = msg.input_values
        if "icon_source" not in values:
            return await super().handle_additional_configuration_response(msg)

        if self._pending_device_config is None:
            return SetupError(error_type=IntegrationSetupError.OTHER)

        saved_index = self._option_index
        existing = (
            self._pending_device_config.options[saved_index]
            if saved_index < len(self._pending_device_config.options)
            else None
        )

        try:
            source, icon_ref, image_value = await self._resolve_selected_icon(
                values, existing
            )
        except Exception as exc:  # noqa: BLE001 - shown as an in-flow validation error
            _LOG.warning("Invalid option icon configuration: %s", exc)
            return self._build_option_retry_screen(
                f"Icon validation failed: {exc}",
                values,
            )

        # Only user-supplied Base64 should go through the legacy Base64 input path.
        # UC and Remote resource icons have already been resolved and validated by the
        # icon resolver. Passing those generated data URIs through the old option saver
        # needlessly couples native/resource icons to legacy input validation.
        values["image_base64"] = image_value if source == "base64" else ""

        result = await super().handle_additional_configuration_response(msg)
        if isinstance(result, SetupError):
            return self._build_option_retry_screen(
                "Option validation failed. Check the option name, target entity, "
                "command ID, command parameters and selected icon source.",
                values,
            )

        if saved_index < len(self._pending_device_config.options):
            saved = self._pending_device_config.options[saved_index]
            saved.icon = icon_ref
            if source in {"uc", "resource"}:
                saved.image_base64 = image_value
            elif source == "none":
                saved.image_base64 = ""

        return result