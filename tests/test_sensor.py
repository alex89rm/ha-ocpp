"""Test sensor for ocpp integration."""

import asyncio
import websockets
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.components.sensor.const import (
    SensorDeviceClass,
    SensorStateClass,
    ATTR_STATE_CLASS,
)

from custom_components.ocpp.const import (
    CONF_CSID,
    CONF_NUM_CONNECTORS,
    DOMAIN as OCPP_DOMAIN,
)

from .const import (
    MOCK_CONFIG_DATA,
    CONF_CPIDS,
    MOCK_CONFIG_CP_APPEND,
    CONF_PORT,
    CONF_CPID,
)
from .charge_point_test import create_configuration, remove_configuration


async def test_central_system_has_diagnostic_sensor_without_chargers(
    hass, socket_enabled
):
    """The parent device explains the running listener before discovery."""
    data = {
        **MOCK_CONFIG_DATA,
        CONF_CSID: "test_central_status",
        CONF_CPIDS: [],
        CONF_PORT: 9060,
    }
    config_entry = MockConfigEntry(
        domain=OCPP_DOMAIN,
        data=data,
        entry_id="test_central_status",
        title="test_central_status",
        version=2,
        minor_version=1,
    )

    await create_configuration(hass, config_entry)

    state = hass.states.get("sensor.test_central_status_server_status")
    assert state is not None
    assert state.state == "running"
    assert state.attributes["listen_address"] == data["host"]
    assert state.attributes["listen_port"] == 9060
    assert state.attributes["secure"] is False
    assert state.attributes["websocket_scheme"] == "ws"
    assert state.attributes["charge_point_path"] == "/{charge_point_id}"
    assert state.attributes["configured_charge_points"] == {}
    assert state.attributes["available_charge_points"] == {}
    assert state.attributes["accepted_subprotocols"] == [
        "ocpp1.6",
        "ocpp2.0.1",
        "ocpp2.1",
    ]

    await remove_configuration(hass, config_entry)


async def test_sensor(hass, socket_enabled):
    """Test sensor."""

    cp_id = "CP_1_sens"
    cpid = "test_cpid_sens"
    data = {**MOCK_CONFIG_DATA, CONF_CPIDS: []}
    cp_data = MOCK_CONFIG_CP_APPEND.copy()
    cp_data[CONF_CPID] = cpid
    data[CONF_CPIDS].append({cp_id: cp_data})
    data[CONF_PORT] = 9515
    config_entry = MockConfigEntry(
        domain=OCPP_DOMAIN,
        data=data,
        entry_id="test_cms_sens",
        title="test_cms_sens",
        version=2,
        minor_version=0,
    )

    # start clean entry for server
    await create_configuration(hass, config_entry)
    server_state = hass.states.get("sensor.test_csid_server_status")
    assert server_state.attributes["configured_charge_points"] == {cp_id: cpid}

    # connect to websocket to trigger charger setup
    async with websockets.connect(
        f"ws://127.0.0.1:{data[CONF_PORT]}/{cp_id}",
        subprotocols=["ocpp1.6"],
    ) as ws:
        # Wait for setup to complete
        await asyncio.sleep(1)
        # Test reactive power sensor
        state = hass.states.get(f"sensor.{cpid}_power_reactive_import")
        assert (
            state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.REACTIVE_POWER
        )
        assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT
        # Test reactive energy sensor, not having own device class yet
        state = hass.states.get(f"sensor.{cpid}_energy_reactive_import_register")
        assert state.attributes.get(ATTR_DEVICE_CLASS) is None
        assert state.attributes.get(ATTR_STATE_CLASS) is None

        await ws.close()

    await remove_configuration(hass, config_entry)


async def test_sensor_entities_per_connector_created(hass, socket_enabled):
    """Create separate entities per connector when num_connectors=2."""

    cp_id = "CP_1_sens_mc"
    cpid = "test_cpid_sens_mc"

    data = {**MOCK_CONFIG_DATA, CONF_CPIDS: []}
    cp_data = MOCK_CONFIG_CP_APPEND.copy()
    cp_data[CONF_CPID] = cpid
    cp_data[CONF_NUM_CONNECTORS] = 2  # ensure two connectors up front
    data[CONF_CPIDS].append({cp_id: cp_data})
    data[CONF_PORT] = 9050

    config_entry = MockConfigEntry(
        domain=OCPP_DOMAIN,
        data=data,
        entry_id="test_cms_sens_mc",
        title="test_cms_sens_mc",
        version=2,
        minor_version=0,
    )

    await create_configuration(hass, config_entry)

    # Open a ws once to trigger platform setup; entities are created during setup_entry
    async with websockets.connect(
        f"ws://127.0.0.1:{data[CONF_PORT]}/{cp_id}",
        subprotocols=["ocpp1.6"],
    ) as ws:
        # Give HA a tick to register entities
        await asyncio.sleep(0.5)

        # Per-connector entities should include <cpid> in the entity_id
        s1 = hass.states.get(f"sensor.{cpid}_connector_1_status_connector")
        s2 = hass.states.get(f"sensor.{cpid}_connector_2_status_connector")
        assert s1 is not None, "missing sensor for connector 1"
        assert s2 is not None, "missing sensor for connector 2"

        # There must not be any entity for a non-existent connector 3
        s3 = hass.states.get(f"sensor.{cpid}_connector_3_status_connector")
        assert s3 is None, "unexpected sensor for connector 3"

        # Root-level sensor still includes <cpid>
        root = hass.states.get(f"sensor.{cpid}_connectors")
        assert root is not None, "missing root-level 'connectors' sensor"

        await ws.close()

    await remove_configuration(hass, config_entry)
