"""Tests for custom Select device lifecycle behavior."""

from ucapi.select import Attributes as SelectAttr
from ucapi.select import States
from ucapi_framework.device import DeviceEvents

from uc_intg_custom_select.config import CustomSelectConfig
from uc_intg_custom_select.device import CustomSelectDevice


def _config() -> CustomSelectConfig:
    return CustomSelectConfig(
        identifier="availability-test",
        name="Availability Test",
        remote_url="http://127.0.0.1:8080",
        api_key="test-key",
    )


async def test_connect_pushes_available_state(monkeypatch) -> None:
    """Successful connection must notify coordinator entities after connection."""
    device = CustomSelectDevice(_config())
    updates: list[dict] = []

    async def verify_connection() -> None:
        return None

    monkeypatch.setattr(device, "verify_connection", verify_connection)
    device.events.on(
        DeviceEvents.UPDATE,
        lambda: updates.append(
            device.get_device_attributes("select.availability-test")
        ),
    )

    before = device.get_device_attributes("select.availability-test")
    assert before[SelectAttr.STATE] == States.UNAVAILABLE

    assert await device.connect() is True

    assert device.is_connected is True
    assert len(updates) == 1
    assert updates[0][SelectAttr.STATE] == States.ON
