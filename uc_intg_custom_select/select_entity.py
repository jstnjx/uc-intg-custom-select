"""UC Select entity exposing Base64-backed styled options."""

import logging
from typing import Any

from ucapi import EntityTypes, Select, StatusCodes
from ucapi.select import Attributes as SelectAttr
from ucapi.select import Commands as SelectCommands
from ucapi_framework import Entity, create_entity_id

from .config import CustomSelectConfig
from .device import CustomSelectDevice

_LOG = logging.getLogger(__name__)


class CustomSelectEntity(Select, Entity):
    """A custom Select whose options dispatch commands to existing Remote entities."""

    def __init__(
        self,
        device_config: CustomSelectConfig,
        device: CustomSelectDevice,
    ) -> None:
        self._device = device
        entity_id = create_entity_id(EntityTypes.SELECT, device_config.identifier)

        super().__init__(
            identifier=entity_id,
            name=device_config.name,
            icon="uc:list",
            description="Styled custom select with inline Base64 option images",
            attributes=device.get_device_attributes(entity_id),
            cmd_handler=self.handle_command,
        )
        self.subscribe_to_device(device)

    async def handle_command(
        self,
        entity: Select,
        cmd_id: str,
        params: dict[str, Any] | None,
        _: Any | None = None,
    ) -> StatusCodes:
        del entity

        options = self._device.option_values
        if not options:
            return StatusCodes.BAD_REQUEST

        current = self._device.get_device_attributes(self.id).get(
            SelectAttr.CURRENT_OPTION, ""
        )
        cycle = bool(params.get("cycle")) if params else False
        target: str | None = None

        match cmd_id:
            case SelectCommands.SELECT_OPTION:
                target = str(params.get("option", "")) if params else ""
            case SelectCommands.SELECT_FIRST:
                target = options[0]
            case SelectCommands.SELECT_LAST:
                target = options[-1]
            case SelectCommands.SELECT_NEXT:
                if current in options:
                    index = options.index(current)
                    if index < len(options) - 1:
                        target = options[index + 1]
                    elif cycle:
                        target = options[0]
                else:
                    target = options[0]
            case SelectCommands.SELECT_PREVIOUS:
                if current in options:
                    index = options.index(current)
                    if index > 0:
                        target = options[index - 1]
                    elif cycle:
                        target = options[-1]
                else:
                    target = options[-1]
            case _:
                _LOG.warning("[%s] Unsupported command: %s", self.id, cmd_id)
                return StatusCodes.NOT_IMPLEMENTED

        if not target or target not in options:
            return StatusCodes.BAD_REQUEST

        if not await self._device.execute_option(target):
            return StatusCodes.BAD_REQUEST

        await self.sync_state()
        return StatusCodes.OK

    async def sync_state(self) -> None:
        self.update(self._device.get_device_attributes(self.id))
