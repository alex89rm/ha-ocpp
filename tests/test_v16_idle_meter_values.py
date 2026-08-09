"""Test OCPP 1.6 idle MeterValues refreshes."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from websockets.protocol import State

from ocpp.v16.enums import MessageTrigger

from custom_components.ocpp.const import (
    DOMAIN,
    CentralSystemSettings,
    ChargerSystemSettings,
)
from custom_components.ocpp.enums import Profiles
from custom_components.ocpp.ocppv16 import ChargePoint

from .const import CONF_SSL_CERTFILE_PATH, CONF_SSL_KEYFILE_PATH


def _make_charge_point(hass, *, idle_interval: int = 60) -> ChargePoint:
    """Build a minimal OCPP 1.6 charge point."""
    data = {
        "host": "127.0.0.1",
        "port": 0,
        "csid": "cs",
        "cpids": [{"CP_A": {"cpid": "test_cpid"}}],
        "subprotocols": ["ocpp1.6"],
        "websocket_close_timeout": 5,
        "ssl": False,
        "websocket_ping_interval": 0.0,
        "websocket_ping_timeout": 0.01,
        "websocket_ping_tries": 0,
        "ssl_certfile_path": CONF_SSL_CERTFILE_PATH,
        "ssl_keyfile_path": CONF_SSL_KEYFILE_PATH,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    central = CentralSystemSettings(**data)
    charger = ChargerSystemSettings(
        cpid="test_cpid",
        max_current=32,
        idle_interval=idle_interval,
        meter_interval=60,
        monitored_variables="",
        monitored_variables_autoconfig=False,
        skip_schema_validation=False,
        force_smart_charging=False,
    )
    connection = SimpleNamespace(
        state=State.OPEN,
        close=lambda: asyncio.sleep(0),
        wait_closed=lambda: asyncio.sleep(3600),
    )
    charge_point = ChargePoint("CP_A", connection, hass, entry, central, charger)
    charge_point.post_connect_success = True
    charge_point._attr_supported_features = Profiles.REM
    return charge_point


async def test_request_idle_meter_values_when_supported(hass):
    """An idle RemoteTrigger charger receives a MeterValues request."""
    charge_point = _make_charge_point(hass)
    charge_point.trigger_custom_message = AsyncMock(return_value=True)

    assert await charge_point._request_idle_meter_values() is True
    charge_point.trigger_custom_message.assert_awaited_once_with(
        MessageTrigger.meter_values
    )


async def test_request_idle_meter_values_skips_active_transaction(hass):
    """No idle refresh is sent while any connector is charging."""
    charge_point = _make_charge_point(hass)
    charge_point._active_tx = {1: 0, 2: 42}
    charge_point.trigger_custom_message = AsyncMock(return_value=True)

    assert await charge_point._request_idle_meter_values() is False
    charge_point.trigger_custom_message.assert_not_awaited()


async def test_request_idle_meter_values_requires_remote_trigger(hass):
    """Unsupported chargers and a disabled interval are left untouched."""
    charge_point = _make_charge_point(hass)
    charge_point._attr_supported_features = Profiles.CORE
    charge_point.trigger_custom_message = AsyncMock(return_value=True)

    assert await charge_point._request_idle_meter_values() is False

    charge_point._attr_supported_features = Profiles.REM
    charge_point.settings.idle_interval = 0
    assert await charge_point._request_idle_meter_values() is False
    charge_point.trigger_custom_message.assert_not_awaited()


async def test_post_transaction_refresh_uses_short_delay(hass):
    """Stopping a transaction schedules a prompt idle snapshot."""
    charge_point = _make_charge_point(hass)
    charge_point._request_idle_meter_values = AsyncMock(return_value=True)

    with patch(
        "custom_components.ocpp.ocppv16.asyncio.sleep", new=AsyncMock()
    ) as sleep:
        await charge_point._request_idle_meter_values_after_stop()

    sleep.assert_awaited_once_with(1)
    charge_point._request_idle_meter_values.assert_awaited_once_with()


async def test_stop_transaction_schedules_idle_refresh(hass):
    """The OCPP StopTransaction handler starts an idle refresh."""
    charge_point = _make_charge_point(hass)
    charge_point._init_connector_slots(1)
    charge_point._active_tx[1] = 42
    charge_point.update = AsyncMock()
    charge_point._request_idle_meter_values_after_stop = AsyncMock()

    charge_point.on_stop_transaction(
        meter_stop=0,
        timestamp="2026-08-09T12:00:00Z",
        transaction_id=42,
    )
    await hass.async_block_till_done()

    charge_point._request_idle_meter_values_after_stop.assert_awaited_once_with()


async def test_idle_monitor_uses_configured_interval(hass):
    """The options-flow idle interval controls the polling cadence."""
    charge_point = _make_charge_point(hass, idle_interval=20)

    async def close_after_request():
        charge_point._connection.state = State.CLOSED
        return True

    charge_point._request_idle_meter_values = AsyncMock(side_effect=close_after_request)

    async def expire_interval(awaitable, *, timeout):
        awaitable.close()
        assert timeout == 20
        raise TimeoutError

    with patch(
        "custom_components.ocpp.ocppv16.asyncio.wait_for",
        side_effect=expire_interval,
    ) as wait_for:
        await charge_point.monitor_idle_meter_values()

    wait_for.assert_awaited_once()
    charge_point._request_idle_meter_values.assert_awaited_once_with()


async def test_idle_monitor_exits_when_connection_closes(hass):
    """A closed WebSocket interrupts the monitor without waiting for polling."""
    charge_point = _make_charge_point(hass)
    charge_point._connection.wait_closed = AsyncMock()
    charge_point._request_idle_meter_values = AsyncMock(return_value=True)

    await charge_point.monitor_idle_meter_values()

    charge_point._connection.wait_closed.assert_awaited_once_with()
    charge_point._request_idle_meter_values.assert_not_awaited()
