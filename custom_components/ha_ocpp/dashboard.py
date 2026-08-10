"""Administrative dashboard and websocket API for HA OCPP."""

from __future__ import annotations

import copy
import logging

from pathlib import Path
from typing import Any

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.util import slugify
from ocpp.v16.enums import AuthorizationStatus, Measurand
import voluptuous as vol

from .api import CentralSystem
from .authorization import (
    AUTHORIZATION_STATUSES,
    AuthorizationRegistryError,
)
from .const import (
    CHARGING_RATE_UNIT_CURRENT,
    CHARGING_RATE_UNIT_POWER,
    CONF_CPIDS,
    CONF_CPID,
    CONF_CHARGING_RATE_UNITS,
    CONF_HOST,
    CONF_IDLE_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_MAX_POWER,
    CONF_METER_INTERVAL,
    CONF_NUM_CONNECTORS,
    CONF_PORT,
    CONF_SSL,
    CONF_SSL_CERTFILE_PATH,
    CONF_SSL_KEYFILE_PATH,
    CONF_WALLBOX_PROFILE,
    CONF_WEBSOCKET_CLOSE_TIMEOUT,
    CONF_WEBSOCKET_PING_INTERVAL,
    CONF_WEBSOCKET_PING_TIMEOUT,
    CONF_WEBSOCKET_PING_TRIES,
    DASHBOARD_UPDATED,
    DATA_UPDATED,
    DOMAIN,
    split_charging_rate_units,
)
from .enums import (
    HAChargerServices as csvcs,
    HAChargerSession as csess,
    HAChargerStatuses as cstat,
)
from .wallbox_profiles import (
    AUTO_PROFILE_ID,
    WallboxIdentity,
    profile_catalog,
    select_profile,
)

_LOGGER = logging.getLogger(__package__)

PANEL_URL_PATH = "ha-ocpp"
PANEL_STATIC_URL = "/ha_ocpp_static"
PANEL_ELEMENT = "ha-ocpp-panel"
PANEL_REGISTERED = "dashboard_registered"
PANEL_DIRECTORY = Path(__file__).parent / "frontend"


def _available_connector_actions(status: Any, connected: bool) -> tuple[str, ...]:
    """Return commands that make sense for the connector's current state."""
    if not connected:
        return ()
    normalized = "".join(
        character for character in str(status or "").casefold() if character.isalnum()
    )
    if normalized in {"charging", "suspendedev", "suspendedevse"}:
        return ("stop",)
    if normalized == "preparing":
        return ("start", "unlock")
    if normalized == "finishing":
        return ("unlock",)
    if normalized in {"", "available"}:
        return ("start",)
    return ()


def _central_system(hass: HomeAssistant) -> CentralSystem | None:
    """Return the single loaded HA OCPP server."""
    return next(
        (
            value
            for value in hass.data.get(DOMAIN, {}).values()
            if isinstance(value, CentralSystem)
        ),
        None,
    )


def _central_by_entry(hass: HomeAssistant, entry_id: str) -> CentralSystem | None:
    """Return one loaded central system by config entry id."""
    value = hass.data.get(DOMAIN, {}).get(entry_id)
    return value if isinstance(value, CentralSystem) else None


def _metric(
    central: CentralSystem,
    cpid: str,
    measurand: str,
    connector_id: int | None,
) -> dict[str, Any]:
    """Return a JSON-safe metric value and unit."""
    return {
        "value": central.get_metric(cpid, measurand, connector_id=connector_id),
        "unit": central.get_ha_unit(cpid, measurand, connector_id=connector_id),
    }


def _number_entity_id(
    hass: HomeAssistant,
    cpid: str,
    key: str,
    connector_id: int | None = None,
) -> str | None:
    """Resolve a number entity through its stable unique id."""
    unique_parts = ["number", DOMAIN, cpid, key]
    if connector_id is not None:
        unique_parts.insert(3, f"conn{connector_id}")
    registry = entity_registry.async_get(hass)
    entity_id = registry.async_get_entity_id(
        NUMBER_DOMAIN, DOMAIN, ".".join(unique_parts)
    )
    if entity_id is not None:
        return entity_id

    fallback = f"{cpid}_{key}"
    if connector_id is not None:
        fallback = f"{cpid}_connector_{connector_id}_{key}"
    entity_id = f"{NUMBER_DOMAIN}.{slugify(fallback)}"
    return entity_id if hass.states.get(entity_id) is not None else None


def _number_state(
    hass: HomeAssistant,
    cpid: str,
    key: str,
    connector_id: int | None = None,
) -> float | None:
    """Return a number entity state through its stable unique id."""
    entity_id = _number_entity_id(hass, cpid, key, connector_id)
    if entity_id is None:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in {"unknown", "unavailable"}:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _authorization_snapshot(central: CentralSystem) -> dict[str, Any]:
    """Return users and RFID metadata for the admin-only dashboard."""
    users = []
    for user_id, user in central.authorization.users.items():
        users.append(
            {
                "id": user_id,
                "name": user["name"],
                "enabled": user["enabled"],
                "credentials": [
                    {
                        "id": credential["id"],
                        "label": credential["label"],
                        "enabled": credential["enabled"],
                        "authorization_status": credential["authorization_status"],
                        "token": credential["token"],
                    }
                    for credential in user["credentials"]
                ],
            }
        )
    users.sort(key=lambda item: item["name"].casefold())
    pending = [
        {
            "id": item["id"],
            "cp_id": item["cp_id"],
            "created_at": item["created_at"],
            "token": item["token"],
        }
        for item in central.authorization.pending_credentials
    ]
    return {
        "registered_only": central.authorization.registered_only,
        "users": users,
        "pending_credentials": pending,
        "enrollments": central.authorization.active_enrollments,
        "statuses": list(AUTHORIZATION_STATUSES),
    }


def _wallbox_snapshot(
    hass: HomeAssistant,
    central: CentralSystem,
    cp_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Build one normalized wallbox record for the frontend."""
    cpid = config[CONF_CPID]
    charge_point = central.charge_points.get(cp_id)
    registry = device_registry.async_get(hass)
    device = registry.async_get_device({(DOMAIN, cp_id), (DOMAIN, cpid)})

    if charge_point is not None:
        identity = charge_point.wallbox_identity
        profile = charge_point.wallbox_profile
        connected = central.get_available(cpid, connector_id=0) is True
        protocol = charge_point._ocpp_version
        connector_count = max(1, int(charge_point.num_connectors or 1))
    else:
        identity = WallboxIdentity(
            vendor=str(getattr(device, "manufacturer", "") or ""),
            model=str(getattr(device, "model", "") or ""),
            firmware_version=str(getattr(device, "sw_version", "") or ""),
        )
        profile = select_profile(identity, config.get(CONF_WALLBOX_PROFILE))
        connected = False
        protocol = None
        connector_count = max(1, int(config.get(CONF_NUM_CONNECTORS, 1) or 1))

    connectors = []
    for connector_id in range(1, connector_count + 1):
        connector_status = central.get_metric(
            cpid, cstat.status_connector.value, connector_id=connector_id
        )
        connectors.append(
            {
                "id": connector_id,
                "status": connector_status,
                "actions": list(
                    _available_connector_actions(connector_status, connected)
                ),
                "transaction_id": central.get_metric(
                    cpid, csess.transaction_id.value, connector_id=connector_id
                ),
                "power": _metric(
                    central,
                    cpid,
                    Measurand.power_active_import.value,
                    connector_id,
                ),
                "current": _metric(
                    central,
                    cpid,
                    Measurand.current_import.value,
                    connector_id,
                ),
                "voltage": _metric(
                    central, cpid, Measurand.voltage.value, connector_id
                ),
                "energy": _metric(
                    central,
                    cpid,
                    Measurand.energy_active_import_register.value,
                    connector_id,
                ),
                "session_energy": _metric(
                    central, cpid, csess.session_energy.value, connector_id
                ),
                "maximum_current": _number_state(
                    hass, cpid, "maximum_current", connector_id
                ),
            }
        )

    supported_units = list(
        split_charging_rate_units(config.get(CONF_CHARGING_RATE_UNITS))
    )
    return {
        "entry_id": central.entry.entry_id,
        "cp_id": cp_id,
        "cpid": cpid,
        "connected": connected,
        "protocol": protocol,
        "status": central.get_metric(cpid, cstat.status.value, connector_id=0),
        "identity": {
            "vendor": identity.vendor,
            "model": identity.model,
            "serial": identity.serial,
            "firmware_version": identity.firmware_version,
        },
        "profile": profile.as_dict(),
        "profile_override": config.get(CONF_WALLBOX_PROFILE, AUTO_PROFILE_ID),
        "supported_rate_units": supported_units,
        "limits": {
            "maximum_current": _number_state(hass, cpid, "maximum_current"),
            "maximum_power": _number_state(hass, cpid, "maximum_power"),
            "configured_maximum_current": config.get(CONF_MAX_CURRENT),
            "configured_maximum_power": config.get(CONF_MAX_POWER),
        },
        "settings": {
            "meter_interval": config.get(CONF_METER_INTERVAL),
            "idle_interval": config.get(CONF_IDLE_INTERVAL),
        },
        "connectors": connectors,
    }


def dashboard_snapshot(hass: HomeAssistant) -> dict[str, Any]:
    """Return the complete HA OCPP management state."""
    central = _central_system(hass)
    entry = None
    if central is not None:
        wallboxes = [
            _wallbox_snapshot(hass, central, cp_id, config)
            for item in central.entry.data.get(CONF_CPIDS, [])
            for cp_id, config in item.items()
        ]
        entry = {
            "entry_id": central.entry.entry_id,
            "name": central.entry.title,
            "server": {
                "running": central.is_serving,
                "host": central.settings.host,
                "port": central.settings.port,
                "ssl": central.settings.ssl,
                "connections": sum(1 for wallbox in wallboxes if wallbox["connected"]),
                "websocket_ping_interval": central.settings.websocket_ping_interval,
                "websocket_ping_timeout": central.settings.websocket_ping_timeout,
                "websocket_ping_tries": central.settings.websocket_ping_tries,
                "websocket_close_timeout": central.settings.websocket_close_timeout,
            },
            "wallboxes": wallboxes,
            "authorization": _authorization_snapshot(central),
        }
    return {
        "product": "HA OCPP",
        "entry": entry,
        "profiles": profile_catalog(),
    }


@websocket_api.websocket_command({vol.Required("type"): "ha_ocpp/dashboard"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_dashboard(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the management dashboard state."""
    connection.send_result(msg["id"], dashboard_snapshot(hass))


@websocket_api.websocket_command({vol.Required("type"): "ha_ocpp/subscribe"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Subscribe an admin frontend to dashboard changes."""

    @callback
    def forward_update(*_args: Any) -> None:
        connection.send_event(msg["id"], {})

    unsubscribers = [
        async_dispatcher_connect(hass, DATA_UPDATED, forward_update),
        async_dispatcher_connect(hass, DASHBOARD_UPDATED, forward_update),
    ]

    @callback
    def unsubscribe() -> None:
        for unsubscribe_callback in unsubscribers:
            unsubscribe_callback()

    connection.subscriptions[msg["id"]] = unsubscribe
    connection.send_result(msg["id"])


WALLBOX_COMMAND_SCHEMA = {
    vol.Required("type"): "ha_ocpp/wallbox/command",
    vol.Required("entry_id"): str,
    vol.Required("cpid"): str,
    vol.Required("action"): vol.In(
        ["set_limit", "start", "stop", "unlock", "availability"]
    ),
    vol.Optional("value"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional("unit"): vol.In(
        [CHARGING_RATE_UNIT_CURRENT, CHARGING_RATE_UNIT_POWER]
    ),
    vol.Optional("connector_id", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Optional("enabled", default=True): bool,
}


@websocket_api.websocket_command(WALLBOX_COMMAND_SCHEMA)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_wallbox_command(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Execute one bounded wallbox command."""
    central = _central_by_entry(hass, msg["entry_id"])
    if central is None:
        connection.send_error(msg["id"], "entry_not_found", "Server not loaded")
        return
    action = msg["action"]
    connector_id = msg["connector_id"]
    try:
        if action == "set_limit":
            if "value" not in msg or "unit" not in msg:
                raise ValueError("value and unit are required")
            if connector_id > 0 and msg["unit"] != CHARGING_RATE_UNIT_CURRENT:
                raise ValueError("Connector limits currently use amperes")
            key = (
                "maximum_power"
                if msg["unit"] == CHARGING_RATE_UNIT_POWER
                else "maximum_current"
            )
            entity_id = _number_entity_id(
                hass,
                msg["cpid"],
                key,
                connector_id if connector_id > 0 else None,
            )
            if entity_id is None:
                raise ValueError("Maximum charge-rate entity is not available")
            await hass.services.async_call(
                NUMBER_DOMAIN,
                SERVICE_SET_VALUE,
                {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: msg["value"]},
                blocking=True,
            )
            result = True
        else:
            service = {
                "start": csvcs.service_charge_start.name,
                "stop": csvcs.service_charge_stop.name,
                "unlock": csvcs.service_unlock.name,
                "availability": csvcs.service_availability.name,
            }[action]
            operation_connector_id = (
                connector_id if action == "availability" else max(1, connector_id)
            )
            result = await central.set_charger_state(
                msg["cpid"],
                service,
                state=msg["enabled"],
                connector_id=operation_connector_id,
            )
    except Exception as err:
        connection.send_error(msg["id"], "command_failed", str(err))
        return
    if result is not True:
        connection.send_error(
            msg["id"], "command_rejected", "The wallbox rejected the command"
        )
        return
    async_dispatcher_send(hass, DASHBOARD_UPDATED)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_ocpp/wallbox/profile",
        vol.Required("entry_id"): str,
        vol.Required("cp_id"): str,
        vol.Required("profile_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_wallbox_profile(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Persist a wallbox profile override."""
    central = _central_by_entry(hass, msg["entry_id"])
    known_profiles = {AUTO_PROFILE_ID, *(item["id"] for item in profile_catalog())}
    if central is None or msg["profile_id"] not in known_profiles:
        connection.send_error(msg["id"], "invalid_profile", "Unknown profile")
        return
    data = copy.deepcopy(dict(central.entry.data))
    for item in data.get(CONF_CPIDS, []):
        if msg["cp_id"] in item:
            item[msg["cp_id"]][CONF_WALLBOX_PROFILE] = msg["profile_id"]
            hass.config_entries.async_update_entry(central.entry, data=data)
            connection.send_result(msg["id"], {"success": True})
            return
    connection.send_error(msg["id"], "wallbox_not_found", "Wallbox not found")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_ocpp/wallbox/settings",
        vol.Required("entry_id"): str,
        vol.Required("cp_id"): str,
        vol.Optional(CONF_METER_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(CONF_IDLE_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(CONF_MAX_CURRENT): vol.All(vol.Coerce(float), vol.Range(min=1)),
        vol.Optional(CONF_MAX_POWER): vol.All(vol.Coerce(float), vol.Range(min=1)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_wallbox_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update common wallbox settings from the panel."""
    central = _central_by_entry(hass, msg["entry_id"])
    if central is None:
        connection.send_error(msg["id"], "entry_not_found", "Server not loaded")
        return
    data = copy.deepcopy(dict(central.entry.data))
    allowed = {
        CONF_METER_INTERVAL,
        CONF_IDLE_INTERVAL,
        CONF_MAX_CURRENT,
        CONF_MAX_POWER,
    }
    for item in data.get(CONF_CPIDS, []):
        if msg["cp_id"] not in item:
            continue
        item[msg["cp_id"]].update({key: msg[key] for key in allowed if key in msg})
        hass.config_entries.async_update_entry(central.entry, data=data)
        connection.send_result(msg["id"], {"success": True})
        return
    connection.send_error(msg["id"], "wallbox_not_found", "Wallbox not found")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_ocpp/server/settings",
        vol.Required("entry_id"): str,
        vol.Optional(CONF_HOST): str,
        vol.Optional(CONF_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Optional(CONF_SSL): bool,
        vol.Optional(CONF_SSL_CERTFILE_PATH): str,
        vol.Optional(CONF_SSL_KEYFILE_PATH): str,
        vol.Optional(CONF_WEBSOCKET_PING_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional(CONF_WEBSOCKET_PING_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional(CONF_WEBSOCKET_PING_TRIES): vol.All(
            vol.Coerce(int), vol.Range(min=0)
        ),
        vol.Optional(CONF_WEBSOCKET_CLOSE_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_server_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update central-system listener settings."""
    central = _central_by_entry(hass, msg["entry_id"])
    if central is None:
        connection.send_error(msg["id"], "entry_not_found", "Server not loaded")
        return
    allowed = {
        CONF_HOST,
        CONF_PORT,
        CONF_SSL,
        CONF_SSL_CERTFILE_PATH,
        CONF_SSL_KEYFILE_PATH,
        CONF_WEBSOCKET_PING_INTERVAL,
        CONF_WEBSOCKET_PING_TIMEOUT,
        CONF_WEBSOCKET_PING_TRIES,
        CONF_WEBSOCKET_CLOSE_TIMEOUT,
    }
    data = copy.deepcopy(dict(central.entry.data))
    data.update({key: msg[key] for key in allowed if key in msg})
    hass.config_entries.async_update_entry(central.entry, data=data)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_ocpp/authorization/command",
        vol.Required("entry_id"): str,
        vol.Required("action"): vol.In(
            [
                "set_policy",
                "add_user",
                "update_user",
                "delete_user",
                "assign_pending",
                "discard_pending",
                "update_credential",
                "delete_credential",
                "start_enrollment",
            ]
        ),
        vol.Optional("user_id"): str,
        vol.Optional("credential_id"): str,
        vol.Optional("pending_id"): str,
        vol.Optional("cpid"): str,
        vol.Optional("name"): str,
        vol.Optional("label", default=""): str,
        vol.Optional("enabled", default=True): bool,
        vol.Optional("registered_only"): bool,
        vol.Optional(
            "authorization_status", default=AuthorizationStatus.accepted.value
        ): vol.In(AUTHORIZATION_STATUSES),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_authorization_command(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Manage users and RFID credentials through stable record identifiers."""
    central = _central_by_entry(hass, msg["entry_id"])
    if central is None:
        connection.send_error(msg["id"], "entry_not_found", "Server not loaded")
        return
    manager = central.authorization
    action = msg["action"]
    clear_all_caches = False
    try:
        if action == "set_policy":
            await manager.async_set_registered_only(msg["registered_only"])
            clear_all_caches = True
        elif action == "add_user":
            user_id = await manager.async_add_user(msg["name"], msg["enabled"])
            connection.send_result(msg["id"], {"success": True, "user_id": user_id})
            return
        elif action == "update_user":
            await manager.async_update_user(msg["user_id"], msg["name"], msg["enabled"])
            clear_all_caches = True
        elif action == "delete_user":
            await manager.async_delete_user(msg["user_id"])
            clear_all_caches = True
        elif action == "assign_pending":
            _, cp_id = await manager.async_assign_pending(
                msg["pending_id"], msg["user_id"], label=msg["label"]
            )
            await central.clear_authorization_cache(cp_id)
        elif action == "discard_pending":
            await manager.async_discard_pending(msg["pending_id"])
        elif action == "update_credential":
            await manager.async_update_credential(
                msg["credential_id"],
                label=msg["label"],
                enabled=msg["enabled"],
                authorization_status=msg["authorization_status"],
            )
            clear_all_caches = True
        elif action == "delete_credential":
            await manager.async_delete_credential(msg["credential_id"])
            clear_all_caches = True
        elif action == "start_enrollment":
            if not await central.start_rfid_enrollment(msg["cpid"]):
                raise ValueError("Wallbox is not connected")
    except (AuthorizationRegistryError, KeyError, ValueError) as err:
        connection.send_error(msg["id"], "authorization_error", str(err))
        return
    if clear_all_caches:
        for cp_id in central.charge_points:
            await central.apply_authorization_policy(cp_id)
            await central.clear_authorization_cache(cp_id)
    async_dispatcher_send(hass, DASHBOARD_UPDATED)
    connection.send_result(msg["id"], {"success": True})


WEBSOCKET_COMMANDS = (
    websocket_dashboard,
    websocket_subscribe,
    websocket_wallbox_command,
    websocket_wallbox_profile,
    websocket_wallbox_settings,
    websocket_server_settings,
    websocket_authorization_command,
)


async def async_setup_dashboard(hass: HomeAssistant) -> None:
    """Register the admin API and HA OCPP sidebar panel once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(PANEL_REGISTERED):
        return
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                PANEL_STATIC_URL,
                str(PANEL_DIRECTORY),
                cache_headers=False,
            )
        ]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="HA OCPP",
        sidebar_icon="mdi:ev-station",
        module_url=f"{PANEL_STATIC_URL}/ha-ocpp-panel.js",
        require_admin=True,
        config_panel_domain=DOMAIN,
    )
    for command in WEBSOCKET_COMMANDS:
        websocket_api.async_register_command(hass, command)
    domain_data[PANEL_REGISTERED] = True
    _LOGGER.info("HA OCPP management panel registered")
