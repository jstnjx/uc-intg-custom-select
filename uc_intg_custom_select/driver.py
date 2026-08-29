"""Custom integration driver behavior."""

from typing import Any

from ucapi_framework import BaseIntegrationDriver

from .api import FragmentingIntegrationAPI


class CustomSelectDriver(BaseIntegrationDriver):
    """Base driver with large-message-safe Integration API transport."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # BaseIntegrationDriver constructs its own IntegrationAPI and registers event
        # handlers against it. Replace that not-yet-started API before init() and bind
        # the same framework handlers to the fragmented transport implementation.
        self.api = FragmentingIntegrationAPI(self._loop)
        self._setup_event_handlers()
