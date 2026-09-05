"""Custom Select integration entry point."""

import asyncio
import logging
import os

from ucapi_framework import get_config_path

from .config import CustomSelectConfig, CustomSelectConfigManager
from .const import DRIVER_ID, LOGGER_NAME
from .device import CustomSelectDevice
from .driver import CustomSelectDriver
from .select_entity import CustomSelectEntity
from .setup_icons import IconAwareCustomSelectSetupFlow


async def main() -> None:
    """Start the integration."""
    level = os.getenv("UC_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO))
    logging.getLogger(LOGGER_NAME).setLevel(level)

    # BaseSetupFlow logs raw UserDataResponse objects at DEBUG. Setup payloads can
    # contain the Web Configurator PIN and large Base64 images, so never enable
    # framework setup DEBUG logging. The PIN itself is never persisted.
    logging.getLogger("ucapi_framework.setup").setLevel(logging.INFO)

    driver = CustomSelectDriver(
        device_class=CustomSelectDevice,
        entity_classes=[CustomSelectEntity],
        driver_id=DRIVER_ID,
    )

    driver.config_manager = CustomSelectConfigManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        config_class=CustomSelectConfig,
    )

    await driver.register_all_device_instances(connect=False)

    setup_handler = IconAwareCustomSelectSetupFlow.create_handler(driver=driver)
    await driver.api.init("driver.json", setup_handler)

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
