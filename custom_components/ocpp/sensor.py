"""Sensor platform for ocpp."""

from __future__ import annotations

from dataclasses import dataclass
import homeassistant
from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONF_MONITORED_VARIABLES
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.util import slugify

from .api import CentralSystem
from .authorization import mask_token
from .const import (
    CONF_CPID,
    CONF_CPIDS,
    CONF_NUM_CONNECTORS,
    DASHBOARD_UPDATED,
    DATA_UPDATED,
    DEFAULT_CLASS_UNITS_HA,
    DEFAULT_NUM_CONNECTORS,
    DOMAIN,
    ICON,
    Measurand,
)
from .enums import HAChargerDetails, HAChargerSession, HAChargerStatuses


@dataclass
class OcppSensorDescription(SensorEntityDescription):
    """Class to describe a Sensor entity."""

    metric: str | None = None


class CentralSystemStatus(SensorEntity):
    """Diagnostic state and configuration summary for the OCPP listener."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_icon = "mdi:server-network"
    _attr_name = "Server status"
    _attr_should_poll = False

    def __init__(self, central_system: CentralSystem) -> None:
        """Initialize the central-system status sensor."""
        self.central_system = central_system
        self._attr_unique_id = (
            f"{DOMAIN}.{central_system.entry.entry_id}.server_status.sensor"
        )
        self.entity_id = f"{SENSOR_DOMAIN}.{slugify(central_system.id)}_server_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, central_system.id)},
            name=f"OCPP Central System ({central_system.id})",
            model="OCPP Central System",
        )

    @property
    def native_value(self) -> str:
        """Return whether the websocket listener is running."""
        return "running" if self.central_system.is_serving else "stopped"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the listener settings and charger summary."""
        configured_charge_points = {
            cp_id: cp_settings[CONF_CPID]
            for item in self.central_system.entry.data.get(CONF_CPIDS, [])
            for cp_id, cp_settings in item.items()
        }
        available_charge_points = {
            cp_id: cpid
            for cpid, cp_id in self.central_system.cpids.items()
            if self.central_system.get_available(cpid)
        }
        settings = self.central_system.settings
        return {
            "listen_address": settings.host,
            "listen_port": settings.port,
            "secure": settings.ssl,
            "websocket_scheme": "wss" if settings.ssl else "ws",
            "charge_point_path": "/{charge_point_id}",
            "ocpp_version": settings.ocpp_version,
            "accepted_subprotocols": list(self.central_system.subprotocols),
            "configured_charge_points": configured_charge_points,
            "available_charge_points": available_charge_points,
            "websocket_ping_interval": settings.websocket_ping_interval,
            "websocket_ping_timeout": settings.websocket_ping_timeout,
            "websocket_ping_tries": settings.websocket_ping_tries,
        }

    async def async_added_to_hass(self) -> None:
        """Refresh the summary when a charge point updates."""
        await super().async_added_to_hass()

        @callback
        def _update(*_args) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(self.hass, DATA_UPDATED, _update))


class AuthorizationUserStatus(SensorEntity):
    """Charging and authorization state for one registered user."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_has_entity_name = True
    _attr_options = ["idle", "charging", "disabled"]
    _attr_should_poll = False
    _attr_translation_key = "authorization_user_status"

    def __init__(self, central_system: CentralSystem, user_id: str) -> None:
        """Initialize a registered-user status sensor."""
        self.central_system = central_system
        self.user_id = user_id
        user = central_system.authorization.users[user_id]
        self._attr_name = user["name"]
        self._attr_unique_id = (
            f"{DOMAIN}.{central_system.entry.entry_id}.authorization_user."
            f"{user_id}.sensor"
        )
        object_id = slugify(f"{central_system.id}_user_{user['name']}")
        self.entity_id = f"{SENSOR_DOMAIN}.{object_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, central_system.id)},
        )

    def _user(self) -> dict[str, object] | None:
        """Return the current user record."""
        return self.central_system.authorization.users.get(self.user_id)

    def _identity_for_reported_tag(self, reported_tag: object):
        """Resolve both OCPP 1.6 tags and OCPP 2.x type-prefixed tokens."""
        value = str(reported_tag or "")
        if not value:
            return None
        candidates = [value]
        if ":" in value:
            candidates.append(value.split(":", 1)[1])
        for candidate in candidates:
            identity = self.central_system.authorization.identity_for_token(candidate)
            if identity is not None:
                return identity
        return None

    def _active_sessions(self) -> list[dict[str, object]]:
        """Return active OCPP transactions belonging to this user."""
        sessions = []
        for charge_point in self.central_system.charge_points.values():
            cpid = charge_point.settings.cpid
            connector_count = max(1, int(charge_point.num_connectors or 1))
            for connector_id in range(1, connector_count + 1):
                transaction_id = self.central_system.get_metric(
                    cpid,
                    HAChargerSession.transaction_id.value,
                    connector_id=connector_id,
                )
                if transaction_id in (None, "", 0, "0"):
                    continue
                reported_tag = self.central_system.get_metric(
                    cpid,
                    HAChargerStatuses.id_tag.value,
                    connector_id=connector_id,
                )
                identity = self._identity_for_reported_tag(reported_tag)
                if identity is None or identity.user_id != self.user_id:
                    continue
                token = str(reported_tag).split(":", 1)[-1]
                card_name = identity.credential_label or mask_token(token)
                sessions.append(
                    {
                        "charge_point": cpid,
                        "connector_id": connector_id,
                        "transaction_id": transaction_id,
                        "card": card_name,
                    }
                )
        return sessions

    @property
    def available(self) -> bool:
        """Return whether the authorization user still exists."""
        return self._user() is not None

    @property
    def native_value(self) -> str | None:
        """Return disabled, charging, or idle."""
        user = self._user()
        if user is None:
            return None
        if not user["enabled"]:
            return "disabled"
        return "charging" if self._active_sessions() else "idle"

    @property
    def icon(self) -> str:
        """Return an icon matching the user's current state."""
        if self.native_value == "charging":
            return "mdi:account-bolt"
        if self.native_value == "disabled":
            return "mdi:account-off-outline"
        return "mdi:account-outline"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose cards and active charging sessions without leaking RFID codes."""
        user = self._user()
        if user is None:
            return {}
        cards = [
            {
                "name": credential["label"] or mask_token(credential["token"]),
                "identifier": mask_token(credential["token"]),
                "enabled": credential["enabled"],
                "authorization_status": credential["authorization_status"],
            }
            for credential in user["credentials"]
        ]
        return {
            "user_id": self.user_id,
            "enabled": user["enabled"],
            "card_count": len(cards),
            "cards": cards,
            "active_sessions": self._active_sessions(),
        }

    async def async_added_to_hass(self) -> None:
        """Refresh on authorization and OCPP transaction changes."""
        await super().async_added_to_hass()

        @callback
        def _update(*_args) -> None:
            user = self._user()
            if user is None:
                entity_registry = er.async_get(self.hass)
                if entity_registry.async_get(self.entity_id) is not None:
                    entity_registry.async_remove(self.entity_id)
                return
            self._attr_name = user["name"]
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(self.hass, DASHBOARD_UPDATED, _update)
        )
        self.async_on_remove(async_dispatcher_connect(self.hass, DATA_UPDATED, _update))


async def async_setup_entry(hass, entry, async_add_devices):
    """Configure the sensor platform."""
    central_system = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [CentralSystemStatus(central_system)]
    known_user_ids = set(central_system.authorization.users)
    entities.extend(
        AuthorizationUserStatus(central_system, user_id) for user_id in known_user_ids
    )
    ent_reg = er.async_get(hass)

    # setup all chargers added to config
    for charger in entry.data[CONF_CPIDS]:
        cp_id_settings = list(charger.values())[0]
        cpid = cp_id_settings[CONF_CPID]

        num_connectors = 1
        for item in entry.data.get(CONF_CPIDS, []):
            for _, cfg in item.items():
                if cfg.get(CONF_CPID) == cpid:
                    num_connectors = int(
                        cfg.get(CONF_NUM_CONNECTORS, DEFAULT_NUM_CONNECTORS)
                    )
                    break
            else:
                continue
            break

        configured = [
            m.strip()
            for m in str(cp_id_settings.get(CONF_MONITORED_VARIABLES, "")).split(",")
            if m and m.strip()
        ]
        default_measurands: list[str] = []
        measurands = sorted(configured or default_measurands)

        CHARGER_ONLY = [
            HAChargerStatuses.status.value,
            HAChargerStatuses.error_code.value,
            HAChargerStatuses.firmware_status.value,
            HAChargerStatuses.heartbeat.value,
            HAChargerStatuses.id_tag.value,
            HAChargerStatuses.latency_ping.value,
            HAChargerStatuses.latency_pong.value,
            HAChargerStatuses.reconnects.value,
            HAChargerDetails.identifier.value,
            HAChargerDetails.vendor.value,
            HAChargerDetails.model.value,
            HAChargerDetails.serial.value,
            HAChargerDetails.firmware_version.value,
            HAChargerDetails.features.value,
            HAChargerDetails.connectors.value,
            HAChargerDetails.config_response.value,
            HAChargerDetails.data_response.value,
            HAChargerDetails.data_transfer.value,
        ]

        CONNECTOR_ONLY = measurands + [
            HAChargerStatuses.status_connector.value,
            HAChargerStatuses.error_code_connector.value,
            HAChargerStatuses.stop_reason.value,
            HAChargerSession.transaction_id.value,
            HAChargerSession.session_time.value,
            HAChargerSession.session_energy.value,
            HAChargerSession.meter_start.value,
        ]

        def _mk_desc(metric: str, *, cat_diag: bool = False) -> OcppSensorDescription:
            ms = str(metric).strip()
            return OcppSensorDescription(
                key=ms.lower().replace(".", "_"),
                name=ms.replace(".", " "),
                metric=ms,
                entity_category=EntityCategory.DIAGNOSTIC if cat_diag else None,
            )

        def _uid(cpid: str, key: str, connector_id: int | None) -> str:
            """Mirror ChargePointMetric unique_id construction."""
            key = key.lower()
            parts = [DOMAIN, cpid, key, SENSOR_DOMAIN]
            if connector_id is not None:
                parts.insert(2, f"conn{connector_id}")
            return ".".join(parts)

        if num_connectors > 1:
            for metric in CONNECTOR_ONLY:
                uid = _uid(cpid, metric, connector_id=None)
                stale_eid = ent_reg.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, uid)
                if stale_eid:
                    # Remove the old entity so it doesn't linger as 'unavailable'
                    ent_reg.async_remove(stale_eid)

        # Root/charger-entities
        for metric in CHARGER_ONLY:
            entities.append(
                ChargePointMetric(
                    hass,
                    central_system,
                    cpid,
                    _mk_desc(metric, cat_diag=True),
                    connector_id=None,
                )
            )

        if num_connectors > 1:
            for conn_id in range(1, num_connectors + 1):
                for metric in CONNECTOR_ONLY:
                    entities.append(
                        ChargePointMetric(
                            hass,
                            central_system,
                            cpid,
                            _mk_desc(
                                metric,
                                cat_diag=metric
                                in [
                                    HAChargerStatuses.status_connector.value,
                                    HAChargerStatuses.error_code_connector.value,
                                ],
                            ),
                            connector_id=conn_id,
                        )
                    )
        else:
            for metric in CONNECTOR_ONLY:
                entities.append(
                    ChargePointMetric(
                        hass,
                        central_system,
                        cpid,
                        _mk_desc(
                            metric,
                            cat_diag=metric
                            in [
                                HAChargerStatuses.status_connector.value,
                                HAChargerStatuses.error_code_connector.value,
                            ],
                        ),
                        connector_id=None,
                    )
                )

    async_add_devices(entities, False)

    @callback
    def _add_authorization_users(*_args) -> None:
        current_user_ids = set(central_system.authorization.users)
        known_user_ids.intersection_update(current_user_ids)
        new_user_ids = current_user_ids - known_user_ids
        if not new_user_ids:
            return
        known_user_ids.update(new_user_ids)
        async_add_devices(
            [
                AuthorizationUserStatus(central_system, user_id)
                for user_id in new_user_ids
            ],
            False,
        )

    entry.async_on_unload(
        async_dispatcher_connect(hass, DASHBOARD_UPDATED, _add_authorization_users)
    )


class ChargePointMetric(RestoreSensor, SensorEntity):
    """Individual sensor for charge point metrics."""

    _attr_has_entity_name = False
    entity_description: OcppSensorDescription

    def __init__(
        self,
        hass: HomeAssistant,
        central_system: CentralSystem,
        cpid: str,
        description: OcppSensorDescription,
        connector_id: int | None = None,
    ):
        """Instantiate instance of a ChargePointMetrics."""
        self.central_system = central_system
        self.cpid = cpid
        self.entity_description = description
        self.metric = self.entity_description.metric
        self.connector_id = connector_id
        self._hass = hass
        self._extra_attr = {}
        self._last_reset = homeassistant.util.dt.utc_from_timestamp(0)
        parts = [DOMAIN, self.cpid, self.entity_description.key, SENSOR_DOMAIN]
        if self.connector_id is not None:
            parts.insert(2, f"conn{self.connector_id}")
        self._attr_unique_id = ".".join(parts)
        self._attr_name = self.entity_description.name
        if self.connector_id is not None:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{cpid}-conn{self.connector_id}")},
                name=f"{cpid} Connector {self.connector_id}",
                via_device=(DOMAIN, cpid),
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, cpid)},
                name=cpid,
            )

        if self.connector_id is not None:
            object_id = f"{self.cpid}_connector_{self.connector_id}_{self.entity_description.key}"
        else:
            object_id = f"{self.cpid}_{self.entity_description.key}"
        self.entity_id = f"{SENSOR_DOMAIN}.{slugify(object_id)}"
        self._attr_icon = ICON
        self._attr_native_unit_of_measurement = None

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self.central_system.get_available(self.cpid, self.connector_id)

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.

        False if entity pushes its state to HA.
        """
        return False

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self.central_system.get_extra_attr(
            self.cpid, self.metric, self.connector_id
        )

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        state_class = None
        if self.device_class is SensorDeviceClass.ENERGY:
            state_class = SensorStateClass.TOTAL_INCREASING
        elif self.device_class in [
            SensorDeviceClass.CURRENT,
            SensorDeviceClass.VOLTAGE,
            SensorDeviceClass.POWER,
            SensorDeviceClass.REACTIVE_POWER,
            SensorDeviceClass.TEMPERATURE,
            SensorDeviceClass.BATTERY,
            SensorDeviceClass.FREQUENCY,
        ] or self.metric in [
            HAChargerStatuses.latency_ping.value,
            HAChargerStatuses.latency_pong.value,
            HAChargerSession.session_time.value,
        ]:
            state_class = SensorStateClass.MEASUREMENT

        return state_class

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        device_class = None
        if self.metric.lower().startswith("current."):
            device_class = SensorDeviceClass.CURRENT
        elif self.metric.lower().startswith("voltage"):
            device_class = SensorDeviceClass.VOLTAGE
        elif self.metric.lower().startswith("energy.r"):
            device_class = None
        elif self.metric.lower().startswith("energy"):
            device_class = SensorDeviceClass.ENERGY
        elif self.metric in [
            Measurand.frequency,
            Measurand.rpm,
        ] or self.metric.lower().startswith("frequency"):
            device_class = SensorDeviceClass.FREQUENCY
        elif self.metric.lower().startswith(("power.a", "power.o")):
            device_class = SensorDeviceClass.POWER
        elif self.metric.lower().startswith("power.r"):
            device_class = SensorDeviceClass.REACTIVE_POWER
        elif self.metric.lower().startswith("temperature"):
            device_class = SensorDeviceClass.TEMPERATURE
        elif self.metric.lower().startswith("timestamp") or self.metric in [
            HAChargerDetails.config_response.value,
            HAChargerDetails.data_response.value,
            HAChargerStatuses.heartbeat.value,
        ]:
            device_class = SensorDeviceClass.TIMESTAMP
        elif self.metric.lower().startswith("soc"):
            device_class = SensorDeviceClass.BATTERY
        return device_class

    @property
    def native_value(self):
        """Return the state of the sensor, rounding if a number."""
        value = self.central_system.get_metric(
            self.cpid, self.metric, self.connector_id
        )

        # Special case for features - show profiles as labels from IntFlag
        if self.metric == HAChargerDetails.features.value and value is not None:
            if hasattr(value, "labels"):
                self._attr_native_value = value.labels()
            else:
                self._attr_native_value = str(value)

            return self._attr_native_value

        if value is not None:
            self._attr_native_value = value
        return self._attr_native_value

    @property
    def native_unit_of_measurement(self):
        """Return the native unit of measurement."""
        value = self.central_system.get_ha_unit(
            self.cpid, self.metric, self.connector_id
        )
        if value is not None:
            self._attr_native_unit_of_measurement = value
        else:
            self._attr_native_unit_of_measurement = DEFAULT_CLASS_UNITS_HA.get(
                self.device_class
            )
        return self._attr_native_unit_of_measurement

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        if restored := await self.async_get_last_sensor_data():
            self._attr_native_value = restored.native_value
            self._attr_native_unit_of_measurement = restored.native_unit_of_measurement

        @callback
        def _maybe_update(*args):
            active_lookup = None
            if args:
                try:
                    active_lookup = set(args[0])
                except Exception:
                    active_lookup = None

            if active_lookup is None or self.entity_id in active_lookup:
                self.async_schedule_update_ha_state(True)

        self.async_on_remove(
            async_dispatcher_connect(self.hass, DATA_UPDATED, _maybe_update)
        )

        self.async_schedule_update_ha_state(True)
