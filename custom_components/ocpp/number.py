"""Number platform for ocpp."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Final

from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
    NumberEntity,
    NumberEntityDescription,
    RestoreNumber,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

from .api import CentralSystem
from .const import (
    CHARGING_RATE_UNIT_CURRENT,
    CHARGING_RATE_UNIT_POWER,
    CONF_CHARGING_RATE_UNITS,
    CONF_CPID,
    CONF_CPIDS,
    CONF_MAX_CURRENT,
    CONF_MAX_POWER,
    CONF_NUM_CONNECTORS,
    DATA_UPDATED,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_POWER,
    DEFAULT_NUM_CONNECTORS,
    DOMAIN,
    ICON,
    split_charging_rate_units,
)
from .enums import Profiles

_LOGGER: logging.Logger = logging.getLogger(__package__)


@dataclass
class OcppNumberDescription(NumberEntityDescription):
    """Class to describe a Number entity."""

    initial_value: float | None = None


ELECTRIC_CURRENT_AMPERE = UnitOfElectricCurrent.AMPERE
ELECTRIC_POWER_WATT = UnitOfPower.WATT

MAXIMUM_CURRENT: Final = OcppNumberDescription(
    key="maximum_current",
    name="Maximum Current",
    icon=ICON,
    initial_value=DEFAULT_MAX_CURRENT,
    native_min_value=0,
    native_max_value=DEFAULT_MAX_CURRENT,
    native_step=1,
    native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
)
MAXIMUM_POWER: Final = OcppNumberDescription(
    key="maximum_power",
    name="Maximum Power",
    icon=ICON,
    initial_value=DEFAULT_MAX_POWER,
    native_min_value=0,
    native_max_value=DEFAULT_MAX_POWER,
    native_step=10,
    native_unit_of_measurement=ELECTRIC_POWER_WATT,
)

# Existing connector controls remain current-based and connector-scoped.
NUMBERS: Final = [MAXIMUM_CURRENT]
STATION_NUMBERS: Final = [MAXIMUM_CURRENT, MAXIMUM_POWER]

NUMBER_CHARGING_RATE_UNITS: Final = {
    "maximum_current": CHARGING_RATE_UNIT_CURRENT,
    "maximum_power": CHARGING_RATE_UNIT_POWER,
}


async def async_setup_entry(hass, entry, async_add_devices):
    """Configure the number platform."""
    central_system = hass.data[DOMAIN][entry.entry_id]
    entities: list[ChargePointNumber] = []
    ent_reg = er.async_get(hass)

    for charger in entry.data[CONF_CPIDS]:
        cp_id_settings = list(charger.values())[0]
        cpid = cp_id_settings[CONF_CPID]
        supported_units = set(
            split_charging_rate_units(cp_id_settings.get(CONF_CHARGING_RATE_UNITS))
        )

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

        selected_station_numbers = [
            desc
            for desc in STATION_NUMBERS
            if NUMBER_CHARGING_RATE_UNITS[desc.key] in supported_units
        ]

        # Capability detection controls only the new station-wide entities.
        # Connector-scoped controls are an existing feature and must survive.
        for desc in STATION_NUMBERS:
            if desc not in selected_station_numbers:
                uid = ".".join([NUMBER_DOMAIN, DOMAIN, cpid, desc.key])
                stale_eid = ent_reg.async_get_entity_id(NUMBER_DOMAIN, DOMAIN, uid)
                if stale_eid:
                    ent_reg.async_remove(stale_eid)

        def configured_description(desc: OcppNumberDescription):
            if desc.key == "maximum_current":
                maximum = float(
                    cp_id_settings.get(CONF_MAX_CURRENT, DEFAULT_MAX_CURRENT)
                )
            elif desc.key == "maximum_power":
                maximum = float(cp_id_settings.get(CONF_MAX_POWER, DEFAULT_MAX_POWER))
            else:
                maximum = desc.native_max_value

            return OcppNumberDescription(
                key=desc.key,
                name=desc.name,
                icon=desc.icon,
                initial_value=maximum,
                native_min_value=desc.native_min_value,
                native_max_value=maximum,
                native_step=desc.native_step,
                native_unit_of_measurement=desc.native_unit_of_measurement,
            )

        if num_connectors > 1:
            for desc in NUMBERS:
                for conn_id in range(1, num_connectors + 1):
                    entities.append(
                        ChargePointNumber(
                            hass=hass,
                            central_system=central_system,
                            cpid=cpid,
                            description=configured_description(desc),
                            connector_id=conn_id,
                            op_connector_id=conn_id,
                            station_wide=False,
                        )
                    )

        for desc in selected_station_numbers:
            entities.append(
                ChargePointNumber(
                    hass=hass,
                    central_system=central_system,
                    cpid=cpid,
                    description=configured_description(desc),
                    connector_id=None,
                    op_connector_id=0,
                    station_wide=True,
                )
            )

    async_add_devices(entities, False)


class ChargePointNumber(RestoreNumber, NumberEntity):
    """Individual slider for setting charge rate."""

    _attr_has_entity_name = False
    entity_description: OcppNumberDescription

    def __init__(
        self,
        hass: HomeAssistant,
        central_system: CentralSystem,
        cpid: str,
        description: OcppNumberDescription,
        connector_id: int | None = None,
        op_connector_id: int | None = None,
        station_wide: bool = False,
    ):
        """Initialize a Number instance."""
        self.cpid = cpid
        self._hass = hass
        self.central_system = central_system
        self.entity_description = description
        self.connector_id = connector_id
        self._station_wide = station_wide
        self._op_connector_id = (
            op_connector_id if op_connector_id is not None else (connector_id or 1)
        )

        parts = [NUMBER_DOMAIN, DOMAIN, cpid, description.key]
        if self.connector_id:
            parts.insert(3, f"conn{self.connector_id}")
        self._attr_unique_id = ".".join(parts)
        self._attr_name = self.entity_description.name
        if self.connector_id:
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
        self.entity_id = f"{NUMBER_DOMAIN}.{slugify(object_id)}"
        self._attr_native_value = self.entity_description.initial_value
        self._attr_should_poll = False

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if restored := await self.async_get_last_number_data():
            self._attr_native_value = restored.native_value

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        features = self.central_system.get_supported_features(self.cpid)
        has_smart = bool(features & Profiles.SMART)
        return bool(
            self.central_system.get_available(self.cpid, self._op_connector_id)
            and has_smart
        )

    async def async_set_native_value(self, value):
        """Set a connector or station-wide maximum charge rate."""
        self._attr_native_value = float(value)
        self.async_write_ha_state()
        unit = NUMBER_CHARGING_RATE_UNITS[self.entity_description.key]

        try:
            if self._station_wide:
                ok = await self.central_system.set_max_charge_rate(
                    self.cpid,
                    self._attr_native_value,
                    unit,
                )
            else:
                ok = await self.central_system.set_max_charge_rate_amps(
                    self.cpid,
                    self._attr_native_value,
                    connector_id=self._op_connector_id,
                )
            if not ok:
                _LOGGER.warning(
                    "Set %s limit rejected by CP (kept optimistic UI at %s).",
                    unit.lower(),
                    value,
                )
        except Exception as ex:
            _LOGGER.warning(
                "Set %s limit failed: %s (kept optimistic UI at %s).",
                unit.lower(),
                ex,
                value,
            )
