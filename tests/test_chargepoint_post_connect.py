"""Tests for capability persistence after a charge point connects."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ocpp.chargepoint import ChargePoint, OcppVersion
from custom_components.ocpp.const import (
    CHARGING_RATE_UNIT_CURRENT,
    CHARGING_RATE_UNIT_POWER,
    CONF_CHARGING_RATE_UNITS,
    CONF_CPID,
    CONF_CPIDS,
    CONF_MONITORED_VARIABLES,
    CONF_NUM_CONNECTORS,
    DOMAIN,
)


async def test_post_connect_persists_detected_units_without_mutating_entry_data(
    hass, monkeypatch
):
    """Detected units must produce a real config-entry change and reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CPIDS: [
                {
                    "CP_1": {
                        CONF_CPID: "autel",
                        CONF_MONITORED_VARIABLES: "Voltage",
                        CONF_NUM_CONNECTORS: 1,
                        CONF_CHARGING_RATE_UNITS: CHARGING_RATE_UNIT_CURRENT,
                    }
                }
            ]
        },
    )
    entry.add_to_hass(hass)
    original_data = entry.data
    original_settings = entry.data[CONF_CPIDS][0]["CP_1"]

    charge_point = ChargePoint(
        "CP_1",
        None,
        OcppVersion.V16,
        hass,
        entry,
        SimpleNamespace(),
        SimpleNamespace(skip_schema_validation=False, cpid="autel"),
    )
    monkeypatch.setattr(
        charge_point, "fetch_supported_features", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        charge_point, "get_number_of_connectors", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(
        charge_point, "get_heartbeat_interval", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        charge_point, "get_supported_measurands", AsyncMock(return_value="Voltage")
    )
    monkeypatch.setattr(
        charge_point,
        "get_supported_charging_rate_units",
        AsyncMock(return_value=CHARGING_RATE_UNIT_POWER),
    )
    monkeypatch.setattr(
        charge_point, "set_standard_configuration", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(charge_point, "set_availability", AsyncMock(return_value=False))
    monkeypatch.setattr(charge_point, "update", AsyncMock(return_value=None))

    await charge_point.post_connect()
    await hass.async_block_till_done()

    assert original_settings[CONF_CHARGING_RATE_UNITS] == CHARGING_RATE_UNIT_CURRENT
    assert entry.data is not original_data
    assert (
        entry.data[CONF_CPIDS][0]["CP_1"][CONF_CHARGING_RATE_UNITS]
        == CHARGING_RATE_UNIT_POWER
    )
