"""Tests for the HA OCPP management dashboard API."""

import inspect
import json

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er

from custom_components.ha_ocpp.const import (
    CHARGING_RATE_UNIT_CURRENT,
    CHARGING_RATE_UNIT_POWER,
    CONF_CHARGING_RATE_UNITS,
    CONF_CPID,
    CONF_CPIDS,
    CONF_IDLE_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_MAX_POWER,
    CONF_METER_INTERVAL,
    CONF_NUM_CONNECTORS,
    DOMAIN,
)
from custom_components.ha_ocpp.dashboard import (
    PANEL_ICON,
    PANEL_ICON_MODULE,
    WALLBOX_COMMAND_SCHEMA,
    _available_connector_actions,
    _authorization_snapshot,
    async_setup_dashboard,
    dashboard_snapshot,
    websocket_wallbox_command,
)
from custom_components.ha_ocpp.wallbox_profiles import WallboxIdentity, select_profile
import pytest
import voluptuous as vol


RAW_TOKEN = "RFID-SECRET-123456"


async def test_dashboard_registers_material_type2_icon(hass, monkeypatch):
    """The global icon set is loaded before the panel uses its custom icon."""
    register_static_paths = AsyncMock()
    register_panel = AsyncMock()
    add_extra_js_url = Mock()
    register_command = Mock()
    registration_order = Mock()
    registration_order.attach_mock(add_extra_js_url, "add_icon_module")
    registration_order.attach_mock(register_panel, "register_panel")
    hass.http = SimpleNamespace(async_register_static_paths=register_static_paths)
    monkeypatch.setattr(
        "custom_components.ha_ocpp.dashboard.frontend.add_extra_js_url",
        add_extra_js_url,
    )
    monkeypatch.setattr(
        "custom_components.ha_ocpp.dashboard.panel_custom.async_register_panel",
        register_panel,
    )
    monkeypatch.setattr(
        "custom_components.ha_ocpp.dashboard.websocket_api.async_register_command",
        register_command,
    )

    await async_setup_dashboard(hass)

    register_static_paths.assert_awaited_once()
    add_extra_js_url.assert_called_once_with(hass, PANEL_ICON_MODULE)
    register_panel.assert_awaited_once()
    assert register_panel.await_args.kwargs["sidebar_icon"] == PANEL_ICON
    assert [item[0] for item in registration_order.mock_calls[:2]] == [
        "add_icon_module",
        "register_panel",
    ]


def _authorization_manager():
    """Return a dashboard-compatible manager containing sensitive data."""
    return SimpleNamespace(
        registered_only=True,
        users={
            "user-1": {
                "name": "Alessio",
                "enabled": True,
                "credentials": [
                    {
                        "id": "credential-1",
                        "token": RAW_TOKEN,
                        "label": "Auto",
                        "enabled": True,
                        "authorization_status": "Accepted",
                    }
                ],
            }
        },
        pending_credentials=[
            {
                "id": "pending-1",
                "token": "PENDING-SECRET-9876",
                "cp_id": "AUTEL_CP",
                "created_at": "2026-08-09T00:00:00+00:00",
            }
        ],
        active_enrollments=[{"cp_id": "AUTEL_CP", "seconds_remaining": 42}],
    )


def test_authorization_snapshot_exposes_tokens_to_admin_dashboard():
    """The admin-only browser API exposes the RFID code requested by the user."""
    central = SimpleNamespace(authorization=_authorization_manager())

    snapshot = _authorization_snapshot(central)
    serialized = json.dumps(snapshot)

    assert RAW_TOKEN in serialized
    assert "PENDING-SECRET-9876" in serialized
    assert snapshot["users"][0]["credentials"][0]["token"] == RAW_TOKEN


def test_wallbox_command_schema_rejects_negative_connector():
    """Connector commands cannot address an invalid connector id."""
    with pytest.raises(vol.Invalid):
        vol.Schema(WALLBOX_COMMAND_SCHEMA)(
            {
                "type": "ha_ocpp/wallbox/command",
                "entry_id": "entry-1",
                "cpid": "autel",
                "action": "stop",
                "connector_id": -1,
            }
        )


@pytest.mark.parametrize(
    ("unit", "connector_id", "unique_id", "suggested_object_id"),
    [
        (
            CHARGING_RATE_UNIT_POWER,
            0,
            "number.ha_ocpp.autel.maximum_power",
            "autel_maximum_power",
        ),
        (
            CHARGING_RATE_UNIT_CURRENT,
            2,
            "number.ha_ocpp.autel.conn2.maximum_current",
            "autel_connector_2_maximum_current",
        ),
    ],
)
async def test_dashboard_limit_uses_canonical_number_entity(
    hass,
    monkeypatch,
    unit,
    connector_id,
    unique_id,
    suggested_object_id,
):
    """Dashboard limits share the entity's persistence and validation path."""
    registry = er.async_get(hass)
    registry_entry = registry.async_get_or_create(
        NUMBER_DOMAIN,
        DOMAIN,
        unique_id,
        suggested_object_id=suggested_object_id,
    )
    service_calls = []

    async def set_value(call):
        service_calls.append(call.data)

    hass.services.async_register(NUMBER_DOMAIN, SERVICE_SET_VALUE, set_value)
    monkeypatch.setattr(
        "custom_components.ha_ocpp.dashboard._central_by_entry",
        lambda _hass, _entry_id: object(),
    )
    connection = SimpleNamespace(send_result=Mock(), send_error=Mock())
    handler = inspect.unwrap(websocket_wallbox_command)

    await handler(
        hass,
        connection,
        {
            "id": 1,
            "entry_id": "entry-1",
            "cpid": "autel",
            "action": "set_limit",
            "value": 7000.0,
            "unit": unit,
            "connector_id": connector_id,
        },
    )

    assert service_calls == [
        {ATTR_ENTITY_ID: registry_entry.entity_id, ATTR_VALUE: 7000.0}
    ]
    connection.send_error.assert_not_called()
    connection.send_result.assert_called_once_with(1, {"success": True})


@pytest.mark.parametrize(
    ("status", "connected", "actions"),
    [
        ("Available", True, ("start",)),
        ("Preparing", True, ("start", "unlock")),
        ("Charging", True, ("stop",)),
        ("SuspendedEV", True, ("stop",)),
        ("SuspendedEVSE", True, ("stop",)),
        ("Finishing", True, ("unlock",)),
        ("Faulted", True, ()),
        ("Available", False, ()),
    ],
)
def test_connector_actions_follow_the_operational_state(status, connected, actions):
    """The dashboard must not offer contradictory connector commands."""
    assert _available_connector_actions(status, connected) == actions


def test_dashboard_snapshot_exposes_profile_and_each_connector(hass, monkeypatch):
    """The normalized API preserves station and per-connector controls."""
    identity = WallboxIdentity(
        vendor="Autel",
        model="MaxiChargerAC",
        firmware_version="V1.51.00",
    )
    charge_point = SimpleNamespace(
        wallbox_identity=identity,
        wallbox_profile=select_profile(identity),
        _ocpp_version="1.6",
        num_connectors=2,
    )
    config = {
        CONF_CPID: "autel",
        CONF_NUM_CONNECTORS: 2,
        CONF_CHARGING_RATE_UNITS: (
            f"{CHARGING_RATE_UNIT_CURRENT},{CHARGING_RATE_UNIT_POWER}"
        ),
        CONF_MAX_CURRENT: 32,
        CONF_MAX_POWER: 22000,
        CONF_METER_INTERVAL: 10,
        CONF_IDLE_INTERVAL: 60,
    }
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="Garage",
        data={CONF_CPIDS: [{"AUTEL_CP": config}]},
    )
    settings = SimpleNamespace(
        host="0.0.0.0",
        port=9000,
        ssl=False,
        websocket_ping_interval=20,
        websocket_ping_timeout=20,
        websocket_ping_tries=2,
        websocket_close_timeout=10,
    )

    def get_metric(_cpid, metric, **_kwargs):
        return "Charging" if metric == "Status.Connector" else 230

    central = SimpleNamespace(
        entry=entry,
        id="central",
        settings=settings,
        is_serving=True,
        charge_points={"AUTEL_CP": charge_point},
        authorization=_authorization_manager(),
        get_available=lambda *_args, **_kwargs: True,
        get_metric=get_metric,
        get_ha_unit=lambda *_args, **_kwargs: "V",
    )
    monkeypatch.setattr(
        "custom_components.ha_ocpp.dashboard._central_system", lambda _hass: central
    )

    snapshot = dashboard_snapshot(hass)
    wallbox = snapshot["entry"]["wallboxes"][0]

    assert wallbox["profile"]["id"] == "autel.maxicharger"
    assert wallbox["profile"]["hardware_verified"] is True
    assert wallbox["profile"]["product_image"] == (
        "/ha_ocpp_static/assets/autel-maxicharger-ac.png"
    )
    assert wallbox["supported_rate_units"] == ["Current", "Power"]
    assert wallbox["limits"]["configured_maximum_current"] == 32
    assert wallbox["limits"]["configured_maximum_power"] == 22000
    assert [connector["id"] for connector in wallbox["connectors"]] == [1, 2]
    assert [connector["actions"] for connector in wallbox["connectors"]] == [
        ["stop"],
        ["stop"],
    ]
    assert RAW_TOKEN in json.dumps(snapshot)
