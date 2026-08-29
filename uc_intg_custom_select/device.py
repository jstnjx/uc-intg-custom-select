"""Virtual device backing one custom Select entity."""

import logging
from typing import Any

from ucapi.select import Attributes as SelectAttr
from ucapi.select import States
from ucapi_framework import StatelessHTTPDevice
from unfurled.api import CoreAPI

from .config import CustomSelectConfig, SelectOptionConfig
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
        self._current_option = self.option_values[0] if self.option_values else ""

    @property
    def option_values(self) -> list[str]:
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

    def option_for_value(self, option_value: str) -> SelectOptionConfig | None:
        values = self.option_values
        try:
            index = values.index(option_value)
        except ValueError:
            return None
        return self.config.options[index]

    def get_device_attributes(self, entity_id: str) -> dict[str, Any]:
        del entity_id
        return {
            SelectAttr.STATE: States.ON if self.is_connected else States.UNAVAILABLE,
            SelectAttr.CURRENT_OPTION: self._current_option,
            SelectAttr.OPTIONS: self.option_values,
        }

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
