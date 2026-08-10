"""Tests for the simplified OCPP 1.6 set_charge_rate implementation.

These tests use the production ChargePoint class (v1.6) and monkeypatch only
the collaborators set_charge_rate depends on:
- get_configuration(...)
- call(...)
- notify_ha(...)

They avoid any parallel/dummy implementation of ChargePoint.
"""

from types import SimpleNamespace

import pytest

from custom_components.ha_ocpp.ocppv16 import ChargePoint as ChargePointv16
from custom_components.ha_ocpp.const import (
    CHARGING_RATE_UNIT_CURRENT,
    CHARGING_RATE_UNIT_POWER,
)
from custom_components.ha_ocpp.enums import (
    Profiles as prof,
    ConfigurationKey as ckey,
    OcppMisc as om,
)
from ocpp.v16.enums import (
    ChargingProfileStatus,
    ChargingProfilePurposeType,
    ChargingProfileKindType,
    ChargingRateUnitType,
)


@pytest.fixture
def cp_v16():
    """Provide a minimally-initialized v1.6 ChargePoint instance.

    We bypass __init__ and set only the attributes used by set_charge_rate.
    """
    cp = object.__new__(ChargePointv16)  # type: ignore[misc]
    # What set_charge_rate reads:
    cp._attr_supported_features = prof.SMART  # can be overridden in tests
    cp._ocpp_version = "1.6"
    cp.id = "CP_1"
    cp.settings = SimpleNamespace(charging_rate_units=CHARGING_RATE_UNIT_CURRENT)
    cp.active_transaction_id = 0
    cp._active_tx = {}
    # set_charge_rate calls these (we’ll monkeypatch per-test):
    # - cp.get_configuration(key)
    # - cp.call(req)
    # - cp.notify_ha(msg)
    return cp


@pytest.mark.asyncio
async def test_custom_profile_path_exception_triggers_notify_and_returns_false(
    cp_v16, monkeypatch
):
    """1) When a custom profile is provided and the CP call raises, return False and notify HA."""
    # notify capture
    notices = []

    async def fake_notify(msg, title="Ocpp integration"):
        notices.append(msg)
        return True

    async def fake_call(_req):
        raise RuntimeError("boom")

    # get_configuration shouldn't be touched in this path
    async def fake_get_conf(_key):
        pytest.fail("get_configuration should not be called for custom profile")

    monkeypatch.setattr(cp_v16, "notify_ha", fake_notify)
    monkeypatch.setattr(cp_v16, "call", fake_call)
    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)

    profile = {
        "chargingProfileId": 123,
        "stackLevel": 1,
        "chargingProfileKind": ChargingProfileKindType.relative.value,
        "chargingProfilePurpose": ChargingProfilePurposeType.charge_point_max_profile.value,
        "chargingSchedule": {
            "chargingRateUnit": ChargingRateUnitType.amps.value,
            "chargingSchedulePeriod": [{"startPeriod": 0, "limit": 16}],
        },
    }

    ok = await cp_v16.set_charge_rate(profile=profile, conn_id=2)
    assert ok is False
    assert len(notices) == 1
    assert "Set charging profile failed" in notices[0]


@pytest.mark.asyncio
async def test_smart_charging_not_supported_returns_false_no_notify(
    cp_v16, monkeypatch
):
    """2) If the charger doesn't advertise SMART profile, return False without notifications."""
    cp_v16._attr_supported_features = prof.NONE

    notices = []

    async def fake_notify(msg, title="Ocpp integration"):
        notices.append(msg)
        return True

    # get_configuration and call should not be called
    async def fake_get_conf(_key):
        pytest.fail("get_configuration should not be called when SMART not supported")

    async def fake_call(_req):
        pytest.fail("call should not be called when SMART not supported")

    monkeypatch.setattr(cp_v16, "notify_ha", fake_notify)
    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)
    monkeypatch.setattr(cp_v16, "call", fake_call)

    ok = await cp_v16.set_charge_rate(limit_amps=16, conn_id=2)
    assert ok is False
    assert notices == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unit", "advertised", "expected_rate_unit", "limit"),
    [
        (
            CHARGING_RATE_UNIT_CURRENT,
            CHARGING_RATE_UNIT_CURRENT,
            ChargingRateUnitType.amps.value,
            16,
        ),
        (
            CHARGING_RATE_UNIT_POWER,
            CHARGING_RATE_UNIT_POWER,
            ChargingRateUnitType.watts.value,
            2300,
        ),
    ],
)
async def test_set_max_charge_rate_uses_station_wide_absolute_profile(
    cp_v16, monkeypatch, unit, advertised, expected_rate_unit, limit
):
    """Maximum-rate sliders install a persistent station-wide profile."""
    requests = []

    async def fake_get_conf(key: str):
        if key == ckey.charging_schedule_allowed_charging_rate_unit.value:
            return advertised
        if key == ckey.charge_profile_max_stack_level.value:
            return "1"
        pytest.fail(f"Unexpected get_configuration key: {key}")

    async def fake_call(req):
        requests.append(req)
        return SimpleNamespace(status=ChargingProfileStatus.accepted)

    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)
    monkeypatch.setattr(cp_v16, "call", fake_call)

    assert await cp_v16.set_max_charge_rate(limit, unit) is True

    assert len(requests) == 1
    req = requests[0]
    assert req.connector_id == 0
    profile = req.cs_charging_profiles
    assert profile[om.charging_profile_id.value] == 1000
    assert profile[om.stack_level.value] == 1
    assert (
        profile[om.charging_profile_purpose.value]
        == ChargingProfilePurposeType.charge_point_max_profile.value
    )
    assert (
        profile[om.charging_profile_kind.value]
        == ChargingProfileKindType.absolute.value
    )
    assert om.transaction_id.value not in profile
    schedule = profile[om.charging_schedule.value]
    assert schedule[om.charging_rate_unit.value] == expected_rate_unit
    assert schedule[om.charging_schedule_period.value] == [
        {om.start_period.value: 0, om.limit.value: limit}
    ]


@pytest.mark.asyncio
async def test_set_max_charge_rate_rejects_unsupported_unit(cp_v16, monkeypatch):
    """Power requests are rejected before SetChargingProfile on Current-only chargers."""

    async def fake_get_conf(key: str):
        if key == ckey.charging_schedule_allowed_charging_rate_unit.value:
            return CHARGING_RATE_UNIT_CURRENT
        pytest.fail(f"Unexpected get_configuration key: {key}")

    async def fake_call(_req):
        pytest.fail("SetChargingProfile should not be called")

    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)
    monkeypatch.setattr(cp_v16, "call", fake_call)

    assert await cp_v16.set_max_charge_rate(2300, CHARGING_RATE_UNIT_POWER) is False


@pytest.mark.asyncio
async def test_set_max_charge_rate_handles_missing_capability_with_current_fallback(
    cp_v16, monkeypatch
):
    """Missing ChargingScheduleAllowedChargingRateUnit preserves Current fallback."""
    requests = []

    async def fake_get_conf(key: str):
        if key == ckey.charging_schedule_allowed_charging_rate_unit.value:
            return None
        if key == ckey.charge_profile_max_stack_level.value:
            return "1"
        pytest.fail(f"Unexpected get_configuration key: {key}")

    async def fake_call(req):
        requests.append(req)
        return SimpleNamespace(status=ChargingProfileStatus.accepted)

    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)
    monkeypatch.setattr(cp_v16, "call", fake_call)

    assert await cp_v16.set_max_charge_rate(10, CHARGING_RATE_UNIT_CURRENT) is True
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_set_max_charge_rate_returns_false_when_rejected(cp_v16, monkeypatch):
    """Rejected station-wide profiles return False."""

    async def fake_get_conf(key: str):
        if key == ckey.charging_schedule_allowed_charging_rate_unit.value:
            return CHARGING_RATE_UNIT_POWER
        if key == ckey.charge_profile_max_stack_level.value:
            return "1"
        pytest.fail(f"Unexpected get_configuration key: {key}")

    async def fake_call(_req):
        return SimpleNamespace(status=ChargingProfileStatus.rejected)

    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)
    monkeypatch.setattr(cp_v16, "call", fake_call)

    assert await cp_v16.set_max_charge_rate(2300, CHARGING_RATE_UNIT_POWER) is False


@pytest.mark.asyncio
async def test_set_max_charge_rate_requires_smart_charging(cp_v16, monkeypatch):
    """SmartCharging must be advertised or forced."""
    cp_v16._attr_supported_features = prof.NONE

    async def fake_get_conf(_key):
        pytest.fail("get_configuration should not be called")

    async def fake_call(_req):
        pytest.fail("SetChargingProfile should not be called")

    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)
    monkeypatch.setattr(cp_v16, "call", fake_call)

    assert await cp_v16.set_max_charge_rate(16, CHARGING_RATE_UNIT_CURRENT) is False


@pytest.mark.asyncio
async def test_connector_request_skips_cpmax_and_sets_txdefault(cp_v16, monkeypatch):
    """A connector-scoped request must never install a station-wide profile."""

    # Allow both A and stack level
    async def fake_get_conf(key: str):
        if key == ckey.charging_schedule_allowed_charging_rate_unit.value:
            return "Current"  # supports Amps
        if key == ckey.charge_profile_max_stack_level.value:
            return "2"
        pytest.fail(f"Unexpected get_configuration key: {key}")

    requests = []

    async def fake_call(req):
        requests.append(req)
        purpose = req.cs_charging_profiles["chargingProfilePurpose"]
        if purpose == ChargingProfilePurposeType.charge_point_max_profile.value:
            pytest.fail("Connector control must not send ChargePointMaxProfile")
        if purpose == ChargingProfilePurposeType.tx_default_profile.value:
            return SimpleNamespace(status=ChargingProfileStatus.accepted)
        return SimpleNamespace(status=ChargingProfileStatus.rejected)

    notices = []

    async def fake_notify(msg, title="Ocpp integration"):
        notices.append(msg)
        return True

    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)
    monkeypatch.setattr(cp_v16, "call", fake_call)
    monkeypatch.setattr(cp_v16, "notify_ha", fake_notify)

    ok = await cp_v16.set_charge_rate(limit_amps=16, conn_id=2)
    assert ok is True
    assert notices == []
    assert len(requests) == 1
    assert requests[0].connector_id == 2
    assert (
        requests[0].cs_charging_profiles[om.charging_profile_purpose.value]
        == ChargingProfilePurposeType.tx_default_profile.value
    )


@pytest.mark.asyncio
async def test_station_request_keeps_cpmax_fallback(cp_v16, monkeypatch):
    """The legacy station path still falls back when CPMax is rejected."""

    async def fake_get_conf(key: str):
        if key == ckey.charging_schedule_allowed_charging_rate_unit.value:
            return "Current"
        if key == ckey.charge_profile_max_stack_level.value:
            return "3"
        pytest.fail(f"Unexpected get_configuration key: {key}")

    requests = []

    async def fake_call(req):
        requests.append(req)
        purpose = req.cs_charging_profiles["chargingProfilePurpose"]
        if purpose == ChargingProfilePurposeType.charge_point_max_profile.value:
            return SimpleNamespace(status=ChargingProfileStatus.rejected)
        if purpose == ChargingProfilePurposeType.tx_default_profile.value:
            return SimpleNamespace(status=ChargingProfileStatus.accepted)
        return SimpleNamespace(status=ChargingProfileStatus.rejected)

    notices = []

    async def fake_notify(msg, title="Ocpp integration"):
        notices.append(msg)
        return True

    monkeypatch.setattr(cp_v16, "get_configuration", fake_get_conf)
    monkeypatch.setattr(cp_v16, "call", fake_call)
    monkeypatch.setattr(cp_v16, "notify_ha", fake_notify)

    ok = await cp_v16.set_charge_rate(limit_amps=10, conn_id=0)
    assert ok is True
    assert notices == []
    assert [request.connector_id for request in requests] == [0, 1]
