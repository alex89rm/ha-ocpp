"""Tests for the HA OCPP management dashboard API."""

import json

from types import SimpleNamespace

from custom_components.ocpp.const import (
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
)
from custom_components.ocpp.dashboard import (
    WALLBOX_COMMAND_SCHEMA,
    _safe_authorization_snapshot,
    dashboard_snapshot,
)
from custom_components.ocpp.wallbox_profiles import WallboxIdentity, select_profile
import pytest
import voluptuous as vol


RAW_TOKEN = "RFID-SECRET-123456"


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


def test_authorization_snapshot_masks_every_token():
    """The browser API must never receive complete RFID credentials."""
    central = SimpleNamespace(authorization=_authorization_manager())

    snapshot = _safe_authorization_snapshot(central)
    serialized = json.dumps(snapshot)

    assert RAW_TOKEN not in serialized
    assert "PENDING-SECRET-9876" not in serialized
    assert snapshot["users"][0]["credentials"][0]["masked_token"].endswith("3456")
    assert "token" not in snapshot["users"][0]["credentials"][0]


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
    central = SimpleNamespace(
        entry=entry,
        id="central",
        settings=settings,
        is_serving=True,
        charge_points={"AUTEL_CP": charge_point},
        authorization=_authorization_manager(),
        get_available=lambda *_args, **_kwargs: True,
        get_metric=lambda *_args, **_kwargs: 230,
        get_ha_unit=lambda *_args, **_kwargs: "V",
    )
    monkeypatch.setattr(
        "custom_components.ocpp.dashboard._central_systems", lambda _hass: [central]
    )

    snapshot = dashboard_snapshot(hass)
    wallbox = snapshot["entries"][0]["wallboxes"][0]

    assert wallbox["profile"]["id"] == "autel.maxicharger"
    assert wallbox["profile"]["hardware_verified"] is True
    assert wallbox["supported_rate_units"] == ["Current", "Power"]
    assert [connector["id"] for connector in wallbox["connectors"]] == [1, 2]
    assert RAW_TOKEN not in json.dumps(snapshot)
