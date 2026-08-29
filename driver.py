"""Compatibility launcher for environments expecting driver.py."""

import asyncio

from uc_intg_custom_select import main

if __name__ == "__main__":
    asyncio.run(main())
