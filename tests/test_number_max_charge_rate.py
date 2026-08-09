"""Tests for maximum charging-rate number entities."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.helpers import entity_registry as er

from custom_components.ocpp.const import (
    CHARGING_RATE_UNIT_CURRENT,
    CHARGING_RATE_UNIT_POWER,
    CONF_CHARGING_RATE_UNITS,
    CONF_CPID,
    CONF_CPIDS,
    CONF_FORCE_SMART_CHARGING,
    CONF_IDLE_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_MAX_POWER,
    CONF_METER_INTERVAL,
    CONF_MONITORED_VARIABLES,
    CONF_MONITORED_VARIABLES_AUTOCONFIG,
    CONF_NUM_CONNECTORS,
    CONF_SKIP_SCHEMA_VALIDATION,
    DEFAULT_MONITORED_VARIABLES,
    DOMAIN,
)
from custom_components.ocpp.enums import Profiles
from custom_components.ocpp.number import async_setup_entry


class DummyCentralSystem:
    """Minimal central system for number entity tests."""

    def __init__(self) -> None:
        """Initialize."""
        self.station_calls = []
        self.connector_calls = []

    def get_supported_features(self, _cpid: str):
        """Return SmartCharging support."""
        return Profiles.SMART

    def get_available(self, _cpid: str, _connector_id: int | None = None):
        """Return charger availability."""
        return True

    async def set_max_charge_rate(self, cpid: str, value: float, unit: str) -> bool:
        """Record a station-wide max-rate request."""
        self.station_calls.append((cpid, value, unit))
        return True

    async def set_max_charge_rate_amps(
        self, cpid: str, value: float, connector_id: int = 0
    ) -> bool:
        """Record an existing connector-scoped current request."""
        self.connector_calls.append((cpid, value, connector_id))
        return True


def _cp_settings(units: str, *, num_connectors: int = 1) -> dict:
    """Return stored charge point settings."""
    return {
        CONF_CPID: "test_cpid",
        CONF_IDLE_INTERVAL: 900,
        CONF_MAX_CURRENT: 40,
        CONF_MAX_POWER: 7400,
        CONF_METER_INTERVAL: 60,
        CONF_MONITORED_VARIABLES: DEFAULT_MONITORED_VARIABLES,
        CONF_MONITORED_VARIABLES_AUTOCONFIG: True,
        CONF_SKIP_SCHEMA_VALIDATION: False,
        CONF_FORCE_SMART_CHARGING: True,
        CONF_NUM_CONNECTORS: num_connectors,
        CONF_CHARGING_RATE_UNITS: units,
    }


async def _setup_numbers(hass, settings: dict):
    """Set up number entities and return the fake central system plus entities."""
    central = DummyCentralSystem()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CPIDS: [{"CP_1": settings}]},
        entry_id="test_number_entry",
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = central
    entities = []

    def add_devices(new_entities, _update_before_add=False):
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, add_devices)
    return central, entities


async def test_number_entities_follow_current_capability(hass):
    """Current-only chargers expose only Maximum Current."""
    _central, entities = await _setup_numbers(
        hass, _cp_settings(CHARGING_RATE_UNIT_CURRENT)
    )

    assert [entity.entity_description.key for entity in entities] == ["maximum_current"]
    entity = entities[0]
    assert entity._station_wide is True
    assert entity.entity_description.native_unit_of_measurement == (
        UnitOfElectricCurrent.AMPERE
    )
    assert entity.entity_description.native_max_value == 40


async def test_number_entities_follow_power_capability(hass):
    """Power-only chargers expose only Maximum Power."""
    _central, entities = await _setup_numbers(
        hass, _cp_settings(CHARGING_RATE_UNIT_POWER)
    )

    assert [entity.entity_description.key for entity in entities] == ["maximum_power"]
    entity = entities[0]
    assert entity._station_wide is True
    assert entity.entity_description.native_unit_of_measurement == UnitOfPower.WATT
    assert entity.entity_description.native_max_value == 7400
    assert entity.entity_description.native_step == 10


async def test_number_entities_support_both_capabilities(hass):
    """Chargers advertising both units expose both station-wide sliders."""
    _central, entities = await _setup_numbers(
        hass,
        _cp_settings(
            f"{CHARGING_RATE_UNIT_CURRENT},{CHARGING_RATE_UNIT_POWER}",
            num_connectors=3,
        ),
    )

    assert [entity.entity_description.key for entity in entities] == [
        "maximum_current",
        "maximum_current",
        "maximum_current",
        "maximum_current",
        "maximum_power",
    ]
    assert {entity.unique_id for entity in entities} == {
        "number.ocpp.test_cpid.conn1.maximum_current",
        "number.ocpp.test_cpid.conn2.maximum_current",
        "number.ocpp.test_cpid.conn3.maximum_current",
        "number.ocpp.test_cpid.maximum_current",
        "number.ocpp.test_cpid.maximum_power",
    }
    assert [entity.connector_id for entity in entities] == [1, 2, 3, None, None]
    assert [entity._station_wide for entity in entities] == [
        False,
        False,
        False,
        True,
        True,
    ]


async def test_number_setter_uses_generic_station_wide_api(hass, monkeypatch):
    """The Power slider calls the generic max-rate API with connector 0."""
    central, entities = await _setup_numbers(
        hass, _cp_settings(CHARGING_RATE_UNIT_POWER)
    )
    entity = entities[0]
    monkeypatch.setattr(entity, "async_write_ha_state", lambda: None)

    await entity.async_set_native_value(2300)

    assert central.station_calls == [
        ("test_cpid", 2300.0, CHARGING_RATE_UNIT_POWER),
    ]
    assert central.connector_calls == []


async def test_connector_current_controls_are_preserved(hass, monkeypatch):
    """Multi-connector chargers retain one current control per connector."""
    central, entities = await _setup_numbers(
        hass, _cp_settings(CHARGING_RATE_UNIT_POWER, num_connectors=2)
    )
    connector_entities = [entity for entity in entities if entity.connector_id]

    assert [entity.unique_id for entity in connector_entities] == [
        "number.ocpp.test_cpid.conn1.maximum_current",
        "number.ocpp.test_cpid.conn2.maximum_current",
    ]

    entity = connector_entities[1]
    monkeypatch.setattr(entity, "async_write_ha_state", lambda: None)
    await entity.async_set_native_value(20)

    assert central.connector_calls == [("test_cpid", 20.0, 2)]
    assert central.station_calls == []


async def test_number_setup_removes_only_stale_station_entity(hass):
    """Capability cleanup must not delete existing connector controls."""
    ent_reg = er.async_get(hass)
    station_current_uid = "number.ocpp.test_cpid.maximum_current"
    connector_current_uid = "number.ocpp.test_cpid.conn1.maximum_current"
    for unique_id in [station_current_uid, connector_current_uid]:
        ent_reg.async_get_or_create(
            NUMBER_DOMAIN,
            DOMAIN,
            unique_id,
            suggested_object_id=unique_id.replace(".", "_"),
        )

    await _setup_numbers(hass, _cp_settings(CHARGING_RATE_UNIT_POWER, num_connectors=2))

    assert (
        ent_reg.async_get_entity_id(NUMBER_DOMAIN, DOMAIN, station_current_uid) is None
    )
    assert (
        ent_reg.async_get_entity_id(NUMBER_DOMAIN, DOMAIN, connector_current_uid)
        is not None
    )
