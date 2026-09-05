"""Select deletion flow with Remote Core entity cleanup."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from ucapi import IntegrationSetupError, SetupComplete, SetupError
from unfurled.api import CoreAPI

from .config import CustomSelectConfig
from .const import DRIVER_ID
from .setup_icons import IconAwareCustomSelectSetupFlow

_LOG = logging.getLogger(__name__)


class CoreCleanupCustomSelectSetupFlow(IconAwareCustomSelectSetupFlow):
    """Delete both Custom Select configuration and its configured Core entity."""

    async def _handle_configuration_mode(self, msg):
        action = str(msg.input_values.get("action", ""))
        if action != "remove":
            return await super()._handle_configuration_mode(msg)

        # Match the framework's Web Configurator response workaround.
        await asyncio.sleep(1)

        choice = str(msg.input_values.get("choice", "")).strip()
        existing = self.config.get(choice)
        if existing is None:
            return SetupError(error_type=IntegrationSetupError.OTHER)

        try:
            await self._delete_configured_core_entity(existing)
        except Exception as exc:  # noqa: BLE001 - keep local config so deletion can be retried
            _LOG.warning("Could not delete configured Core entity for %s: %s", choice, exc)
            return SetupError(error_type=IntegrationSetupError.OTHER)

        if not self.config.remove(choice):
            _LOG.error(
                "Core entity was deleted but local Select config %s could not be removed",
                choice,
            )
            return SetupError(error_type=IntegrationSetupError.OTHER)

        self._quick_operation = ""
        self._pending_device_config = None
        self._selected_config_id = None
        return SetupComplete()

    async def _delete_configured_core_entity(self, config: CustomSelectConfig) -> None:
        """Delete the configured Remote entity belonging to one Custom Select."""
        expected = f"{DRIVER_ID}.main.select.{config.identifier}"
        suffix = f".select.{config.identifier}"
        prefix = f"{DRIVER_ID}."
        matches: list[str] = []

        async with CoreAPI(config.remote_url, api_key=config.api_key) as api:
            for page in range(1, 101):
                batch = await api.get_entities(limit=100, page=page)
                if not batch:
                    break

                for item in batch:
                    if not isinstance(item, dict):
                        continue
                    entity_id = str(item.get("entity_id") or item.get("id") or "")
                    if entity_id == expected:
                        matches = [entity_id]
                        break
                    if entity_id.startswith(prefix) and entity_id.endswith(suffix):
                        matches.append(entity_id)

                if matches == [expected] or len(batch) < 100:
                    break

            # A Select may never have been configured on the Remote. In that case
            # there is no Core entity to delete and local deletion can continue.
            if not matches:
                _LOG.info("No configured Core entity found for Select %s", config.identifier)
                return

            unique_matches = list(dict.fromkeys(matches))
            if expected in unique_matches:
                entity_id = expected
            elif len(unique_matches) == 1:
                entity_id = unique_matches[0]
            else:
                raise RuntimeError(
                    f"Multiple configured Core entities match Select {config.identifier}: "
                    f"{', '.join(unique_matches)}"
                )

            await api.request(
                "DELETE",
                f"entities/{quote(entity_id, safe='')}",
            )
            _LOG.info("Deleted configured Core entity %s", entity_id)
