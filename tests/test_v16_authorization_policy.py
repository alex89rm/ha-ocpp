"""Tests for OCPP 1.6 charger-side authorization enforcement."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, call

from custom_components.ocpp.chargepoint import SetVariableResult
from custom_components.ocpp.ocppv16 import (
    REGISTERED_ONLY_CONFIGURATION,
    ChargePoint,
)


async def test_registered_only_policy_disables_local_authorization_paths():
    """The central registry must be authoritative before charging starts."""
    charge_point = SimpleNamespace(
        id="AUTEL_CP",
        authorization=SimpleNamespace(registered_only=True),
        configure=AsyncMock(return_value=SetVariableResult.accepted),
    )

    results = await ChargePoint.apply_authorization_policy(charge_point)

    charge_point.configure.assert_has_awaits(
        [call(key, value) for key, value in REGISTERED_ONLY_CONFIGURATION]
    )
    assert results == {key: True for key, _ in REGISTERED_ONLY_CONFIGURATION}


async def test_open_policy_preserves_the_chargers_existing_configuration():
    """Open access must not silently rewrite local/offline behavior."""
    charge_point = SimpleNamespace(
        id="GENERIC_CP",
        authorization=SimpleNamespace(registered_only=False),
        configure=AsyncMock(),
    )

    assert await ChargePoint.apply_authorization_policy(charge_point) == {}
    charge_point.configure.assert_not_awaited()


async def test_unsupported_authorization_setting_is_reported():
    """Callers can see when a charger cannot guarantee central-only access."""
    charge_point = SimpleNamespace(
        id="GENERIC_CP",
        authorization=SimpleNamespace(registered_only=True),
        configure=AsyncMock(
            side_effect=[
                "Unknown",
                *(
                    SetVariableResult.accepted
                    for _ in range(len(REGISTERED_ONLY_CONFIGURATION) - 1)
                ),
            ]
        ),
    )

    results = await ChargePoint.apply_authorization_policy(charge_point)

    first_key = REGISTERED_ONLY_CONFIGURATION[0][0]
    assert results[first_key] is False
    assert all(value is True for key, value in results.items() if key != first_key)
