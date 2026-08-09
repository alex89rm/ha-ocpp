"""OCPP button tests."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ocpp.authorization import EnrollmentInProgressError
from custom_components.ocpp.button import BUTTONS, ChargePointButton


def _learn_rfid_description():
    """Return the RFID enrollment button description."""
    return next(
        description for description in BUTTONS if description.key == "learn_rfid"
    )


async def test_learn_rfid_button_arms_the_correct_charger():
    """The device button starts a station-scoped enrollment session."""
    central = AsyncMock()
    button = ChargePointButton(central, "autel", _learn_rfid_description())

    await button.async_press()

    central.start_rfid_enrollment.assert_awaited_once_with("autel")
    central.set_charger_state.assert_not_awaited()
    assert button.unique_id == "button.ocpp.autel.learn_rfid"
    assert button.translation_key == "learn_rfid"


async def test_learn_rfid_button_reports_an_existing_session():
    """A second press does not replace an options-flow enrollment."""
    central = AsyncMock()
    central.start_rfid_enrollment.side_effect = EnrollmentInProgressError
    button = ChargePointButton(central, "autel", _learn_rfid_description())

    with pytest.raises(HomeAssistantError):
        await button.async_press()
