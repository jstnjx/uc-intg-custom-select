"""Virtual device backing one custom Select entity."""

import logging
from typing import Any

from ucapi.select import Attributes as SelectAttr
from ucapi.select import States
from ucapi_framework import StatelessHTTPDevice
from unfurled.api import CoreAPI

from .config import CustomSelectConfig, SelectOptionConfig
from .icons import get_uc_icon_mapping, option_icon_source, resolve_icon_reference
from .markup import build_option_markup

_LOG = logging.getLogger(__name__)


class CustomSelectDevice(StatelessHTTPDevice):
    """A virtual device whose options execute Core entity commands."""

    @property
    def config(self) -> CustomSelectConfig:
        return self.device_config

    @property
    def identifier(self) -> str:
        return self.config.identifier

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def address(self) -> str:
        return self.config.remote_url

    @property
    def log_id(self) -> str:
        return self.config.identifier

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._option_values = self._render_option_values()

        # Do not duplicate the first image-backed option into current_option during
        # initial state registration. With inline images this can add several KiB to
        # an already large entity_states response. current_option is emitted after
        # the user actually selects an option.
        self._current_option = ""

        rendered_bytes = sum(len(value.encode("utf-8")) for value in self._option_values)
        _LOG.info(
            "[%s] Prepared %d select option(s), %d rendered bytes",
            self.log_id,
            len(self._option_values),
            rendered_bytes,
        )

    def _render_option_values(self) -> list[str]:
        return [
            build_option_markup(
                option,
                self.config.label_style,
                self.config.icon_size,
                self.config.image_alignment,
                self.config.spacing,
            )
            for option in self.config.options
        ]

    @property
    def option_values(self) -> list[str]:
        """Return a copy of the cached rendered option values."""
        return list(self._option_values)

    def option_for_value(self, option_value: str) -> SelectOptionConfig | None:
        try:
            index = self._option_values.index(option_value)
        except ValueError:
            return None
        return self.config.options[index]

    def get_device_attributes(self, entity_id: str) -> dict[str, Any]:
        del entity_id
        attributes: dict[str, Any] = {
            SelectAttr.STATE: States.ON if self.is_connected else States.UNAVAILABLE,
            SelectAttr.OPTIONS: list(self._option_values),
        }
        if self._current_option:
            attributes[SelectAttr.CURRENT_OPTION] = self._current_option
        return attributes

    async def _refresh_icon_cache(self) -> None:
        """Refresh native/resource references while retaining known-good caches."""
        referenced = [option for option in self.config.options if option.icon.strip()]
        if not referenced:
            return

        previous_values = list(self._option_values)
        current_index: int | None = None
        if self._current_option:
            try:
                current_index = previous_values.index(self._current_option)
            except ValueError:
                current_index = None

        uc_mapping: dict[str, Any] | None = None
        changed = False
        async with CoreAPI(self.config.remote_url, api_key=self.config.api_key) as api:
            for option in referenced:
                try:
                    if option_icon_source(option.icon, "") == "uc" and uc_mapping is None:
                        uc_mapping = await get_uc_icon_mapping(api)
                    image = await resolve_icon_reference(
                        api,
                        option.icon,
                        uc_mapping=uc_mapping,
                    )
                    if image != option.image_base64:
                        option.image_base64 = image
                        changed = True
                except Exception as exc:  # noqa: BLE001 - keep known-good cached image
                    _LOG.warning(
                        "[%s] Could not refresh icon %s for option %s: %s",
                        self.log_id,
                        option.icon,
                        option.label,
                        exc,
                    )

        if not changed:
            return

        self._option_values = self._render_option_values()
        if current_index is not None and current_index < len(self._option_values):
            self._current_option = self._option_values[current_index]

        _LOG.info(
            "[%s] Refreshed native/resource icon cache for %d option(s)",
            self.log_id,
            len(referenced),
        )

    async def connect(self) -> bool:
        """Verify Core reachability, refresh icons and propagate availability state."""
        connected = await super().connect()
        if connected:
            await self._refresh_icon_cache()
            # Coordinator-pattern entities are intentionally skipped by the framework's
            # CONNECTED handler. Emit UPDATE after StatelessHTTPDevice has set
            # is_connected=True so subscribed entities run sync_state() and publish ON.
            self.push_update()
        return connected

    async def verify_connection(self) -> None:
        async with CoreAPI(self.config.remote_url, api_key=self.config.api_key) as api:
            await api.get_system_info()

    async def execute_option(self, option_value: str) -> bool:
        option = self.option_for_value(option_value)
        if option is None:
            _LOG.warning("[%s] Unknown select option", self.log_id)
            return False

        try:
            async with CoreAPI(self.config.remote_url, api_key=self.config.api_key) as api:
                await api.put_entity_command(
                    option.target_entity_id,
                    option.command_id,
                    option.params or None,
                )
        except Exception as exc:  # noqa: BLE001 - translated to UC status by entity
            _LOG.error(
                "[%s] Command failed for option %s: %s",
                self.log_id,
                option.label,
                exc,
            )
            return False

        self._current_option = option_value
        self.push_update()
        return True
