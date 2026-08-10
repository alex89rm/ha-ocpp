"""Adds config flow for ocpp."""

import asyncio
import contextlib
from typing import Any
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    CONN_CLASS_LOCAL_PUSH,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from ocpp.v16.enums import AuthorizationStatus

from .authorization import (
    AUTHORIZATION_STATUSES,
    AuthorizationManager,
    CredentialAlreadyAssignedError,
    DuplicateUserNameError,
    EnrollmentInProgressError,
    EnrollmentResult,
    UnknownAuthorizationRecordError,
    mask_token,
)
from .const import (
    CONF_AUTHORIZATION_REQUIRED,
    CONF_AUTH_STATUS,
    CONF_CPID,
    CONF_CPIDS,
    CONF_CHARGING_RATE_UNITS,
    CONF_CSID,
    CONF_FORCE_SMART_CHARGING,
    CONF_HOST,
    CONF_IDLE_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_MAX_POWER,
    CONF_METER_INTERVAL,
    CONF_NAME,
    CONF_MONITORED_VARIABLES,
    CONF_MONITORED_VARIABLES_AUTOCONFIG,
    CONF_NUM_CONNECTORS,
    CONF_OCPP_VERSION,
    CONF_PORT,
    CONF_SKIP_SCHEMA_VALIDATION,
    CONF_SSL,
    CONF_SSL_CERTFILE_PATH,
    CONF_SSL_KEYFILE_PATH,
    CONF_WEBSOCKET_CLOSE_TIMEOUT,
    CONF_WEBSOCKET_PING_INTERVAL,
    CONF_WEBSOCKET_PING_TIMEOUT,
    CONF_WEBSOCKET_PING_TRIES,
    CONF_WALLBOX_PROFILE,
    DEFAULT_CPID,
    DEFAULT_CSID,
    DEFAULT_CHARGING_RATE_UNITS,
    DEFAULT_FORCE_SMART_CHARGING,
    DEFAULT_HOST,
    DEFAULT_IDLE_INTERVAL,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_POWER,
    DEFAULT_MEASURAND,
    DEFAULT_METER_INTERVAL,
    DEFAULT_MONITORED_VARIABLES,
    DEFAULT_MONITORED_VARIABLES_AUTOCONFIG,
    DEFAULT_NUM_CONNECTORS,
    DEFAULT_OCPP_VERSION,
    DEFAULT_PORT,
    DEFAULT_SKIP_SCHEMA_VALIDATION,
    DEFAULT_SSL,
    DEFAULT_SSL_CERTFILE_PATH,
    DEFAULT_SSL_KEYFILE_PATH,
    DEFAULT_WEBSOCKET_CLOSE_TIMEOUT,
    DEFAULT_WEBSOCKET_PING_INTERVAL,
    DEFAULT_WEBSOCKET_PING_TIMEOUT,
    DEFAULT_WEBSOCKET_PING_TRIES,
    DEFAULT_WALLBOX_PROFILE,
    DOMAIN,
    MEASURANDS,
    OCPP_VERSIONS,
)
from .wallbox_profiles import AUTO_PROFILE_ID, profile_catalog


WALLBOX_PROFILE_OPTIONS = {
    AUTO_PROFILE_ID: "Automatic",
    **{item["id"]: item["name"] for item in profile_catalog()},
}


def _central_system_schema(
    current: dict[str, Any] | None = None, *, include_csid: bool
) -> vol.Schema:
    """Build a central-system form with defaults from the current entry."""
    values = current or {}
    fields = {
        vol.Required(CONF_HOST, default=values.get(CONF_HOST, DEFAULT_HOST)): str,
        vol.Required(CONF_PORT, default=values.get(CONF_PORT, DEFAULT_PORT)): int,
        vol.Required(CONF_SSL, default=values.get(CONF_SSL, DEFAULT_SSL)): bool,
        vol.Required(
            CONF_SSL_CERTFILE_PATH,
            default=values.get(CONF_SSL_CERTFILE_PATH, DEFAULT_SSL_CERTFILE_PATH),
        ): str,
        vol.Required(
            CONF_SSL_KEYFILE_PATH,
            default=values.get(CONF_SSL_KEYFILE_PATH, DEFAULT_SSL_KEYFILE_PATH),
        ): str,
    }
    if include_csid:
        fields[vol.Required(CONF_CSID, default=values.get(CONF_CSID, DEFAULT_CSID))] = (
            vol.All(str, vol.Length(max=20))
        )
    fields.update(
        {
            vol.Required(
                CONF_OCPP_VERSION,
                default=values.get(CONF_OCPP_VERSION, DEFAULT_OCPP_VERSION),
            ): vol.In(OCPP_VERSIONS),
            vol.Required(
                CONF_WEBSOCKET_CLOSE_TIMEOUT,
                default=values.get(
                    CONF_WEBSOCKET_CLOSE_TIMEOUT, DEFAULT_WEBSOCKET_CLOSE_TIMEOUT
                ),
            ): int,
            vol.Required(
                CONF_WEBSOCKET_PING_TRIES,
                default=values.get(
                    CONF_WEBSOCKET_PING_TRIES, DEFAULT_WEBSOCKET_PING_TRIES
                ),
            ): int,
            vol.Required(
                CONF_WEBSOCKET_PING_INTERVAL,
                default=values.get(
                    CONF_WEBSOCKET_PING_INTERVAL, DEFAULT_WEBSOCKET_PING_INTERVAL
                ),
            ): int,
            vol.Required(
                CONF_WEBSOCKET_PING_TIMEOUT,
                default=values.get(
                    CONF_WEBSOCKET_PING_TIMEOUT, DEFAULT_WEBSOCKET_PING_TIMEOUT
                ),
            ): int,
        }
    )
    return vol.Schema(fields)


STEP_USER_CS_DATA_SCHEMA = _central_system_schema(include_csid=True)

STEP_USER_CP_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CPID, default=DEFAULT_CPID): str,
        vol.Required(CONF_MAX_CURRENT, default=DEFAULT_MAX_CURRENT): int,
        vol.Required(CONF_MAX_POWER, default=DEFAULT_MAX_POWER): int,
        vol.Required(
            CONF_MONITORED_VARIABLES_AUTOCONFIG,
            default=DEFAULT_MONITORED_VARIABLES_AUTOCONFIG,
        ): bool,
        vol.Required(CONF_METER_INTERVAL, default=DEFAULT_METER_INTERVAL): int,
        vol.Required(CONF_IDLE_INTERVAL, default=DEFAULT_IDLE_INTERVAL): vol.All(
            int, vol.Range(min=0)
        ),
        vol.Optional(CONF_WALLBOX_PROFILE, default=DEFAULT_WALLBOX_PROFILE): vol.In(
            WALLBOX_PROFILE_OPTIONS
        ),
        vol.Required(
            CONF_SKIP_SCHEMA_VALIDATION, default=DEFAULT_SKIP_SCHEMA_VALIDATION
        ): bool,
        vol.Required(
            CONF_FORCE_SMART_CHARGING, default=DEFAULT_FORCE_SMART_CHARGING
        ): bool,
    }
)

STEP_USER_MEASURANDS_SCHEMA = vol.Schema(
    {
        vol.Required(m, default=(True if m == DEFAULT_MEASURAND else False)): bool
        for m in MEASURANDS
    }
)

OPTIONS_TARGET = "target"
OPTIONS_TARGET_CENTRAL_SYSTEM = "__central_system__"
OPTIONS_TARGET_AUTHORIZATION = "__authorization__"

AUTH_ENABLED = "enabled"
AUTH_LABEL = "label"
AUTH_CONFIRM = "confirm"
AUTH_TRANSFER = "transfer"
AUTH_USER_ID = "user_id"
AUTH_CREDENTIAL_ID = "credential_id"
AUTH_PENDING_ID = "pending_id"
AUTH_CHARGE_POINT = "charge_point"


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OCPP."""

    VERSION = 2
    MINOR_VERSION = 3
    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize."""
        self._data: dict[str, Any] = {}
        self._cp_id: str
        self._entry: ConfigEntry
        self._measurands: str = ""
        self._detected_num_connectors: int = DEFAULT_NUM_CONNECTORS

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "OCPPOptionsFlow":
        """Let the settings of an already-configured charge point be edited."""
        return OCPPOptionsFlow()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Handle user central system initiated configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Don't allow servers to use same websocket port
            self._async_abort_entries_match({CONF_PORT: user_input[CONF_PORT]})
            self._data = user_input
            # Add placeholder for cpid settings
            self._data[CONF_CPIDS] = []
            return self.async_create_entry(title=self._data[CONF_CSID], data=self._data)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_CS_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/alex89rm/ha-ocpp"
            },
        )

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        """Allow reconfiguring the central system settings of an existing entry.

        Without this, settings added after an entry was created (such as the
        OCPP version pin) could only be changed by deleting and re-adding the
        integration.
        """
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            # Don't allow servers to use same websocket port (the entry being
            # reconfigured is excluded from the match).
            self._async_abort_entries_match({CONF_PORT: user_input[CONF_PORT]})
            # Updating the entry already triggers a reload, via the
            # add_update_listener(async_reload_entry) registered in
            # async_setup_entry. async_update_reload_and_abort() would schedule
            # a second one on top of it, and the two overlap: the websocket
            # server is rebound while the first setup is still in flight and
            # the platform forwards then fail with "config entry ... has
            # already been setup". Update only, and let the listener reload.
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, **user_input}
            )
            return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_CS_DATA_SCHEMA, entry.data
            ),
            description_placeholders={
                "docs_url": "https://github.com/alex89rm/ha-ocpp"
            },
        )

    async def async_step_integration_discovery(
        self, discovery_info=None
    ) -> ConfigFlowResult:
        """Handle charger discovery initiated configuration."""

        self._entry = discovery_info["entry"]
        self._cp_id = discovery_info["cp_id"]
        self._data = {**self._entry.data}

        self._detected_num_connectors = discovery_info.get(
            CONF_NUM_CONNECTORS, DEFAULT_NUM_CONNECTORS
        )

        await self.async_set_unique_id(self._cp_id)
        # Abort the flow if a config entry with the same unique ID exists
        self._abort_if_unique_id_configured()
        return await self.async_step_cp_user()

    def _other_cpids_in_use(self) -> set[str]:
        """Return every cpid already configured for a charge point other than the current one.

        cpid (as opposed to cp_id, the OCPP-level charge point identity) is
        user-chosen and is what entities' unique_id is built from
        (DOMAIN.cpid.key...), so it must stay unique across every charge
        point of every OCPP config entry, not just within the current
        central system. Only the charge point currently being (re)configured
        -- matched on both its entry and its cp_id -- is excluded, so
        re-submitting its own cpid is not flagged as a duplicate of itself.
        """
        # Match on the entry as well as the charge point: cp_id is the
        # OCPP-level identity, so two central systems can each have one with
        # the same name. Skipping on cp_id alone would also skip the *other*
        # system's record and let a genuine duplicate through.
        own_entry_id = getattr(getattr(self, "_entry", None), "entry_id", None)
        cpids: set[str] = set()
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            for cp_data in entry.data.get(CONF_CPIDS, []):
                for cp_id, cp_settings in cp_data.items():
                    if entry.entry_id == own_entry_id and cp_id == self._cp_id:
                        continue
                    cpids.add(cp_settings[CONF_CPID])
        return cpids

    async def async_step_cp_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure charger by user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate cpid format against entity id requirements (lowercase letters, digits and _)
            schema = vol.Schema(
                {vol.Required(CONF_CPID): cv.matches_regex(r"^[\da-z_]+$")}
            )
            try:
                schema({CONF_CPID: user_input[CONF_CPID]})
            except vol.Invalid:
                errors["base"] = "invalid_cpid"
            else:
                # cpid is used to build entity unique_ids (DOMAIN.cpid.key...)
                # across every OCPP config entry, so it must be unique
                # integration-wide, not just within this central system.
                if user_input[CONF_CPID] in self._other_cpids_in_use():
                    errors["base"] = "duplicate_cpid"

            if not errors:
                cp_data = {
                    **user_input,
                    CONF_NUM_CONNECTORS: self._detected_num_connectors,
                    CONF_CHARGING_RATE_UNITS: DEFAULT_CHARGING_RATE_UNITS,
                }
                cpids_list = self._data.get(CONF_CPIDS, []).copy()
                cpids_list.append({self._cp_id: cp_data})
                self._data = {**self._data, CONF_CPIDS: cpids_list}

                if user_input[CONF_MONITORED_VARIABLES_AUTOCONFIG]:
                    self._data[CONF_CPIDS][-1][self._cp_id][
                        CONF_MONITORED_VARIABLES
                    ] = DEFAULT_MONITORED_VARIABLES
                    self.hass.config_entries.async_update_entry(
                        self._entry, data=self._data
                    )
                    return self.async_abort(reason="Added/Updated charge point")

                else:
                    return await self.async_step_measurands()

        return self.async_show_form(
            step_id="cp_user",
            data_schema=STEP_USER_CP_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/alex89rm/ha-ocpp"
            },
        )

    async def async_step_measurands(self, user_input=None):
        """Select the measurands to be shown."""

        errors: dict[str, str] = {}
        if user_input is not None:
            selected_measurands = [m for m, value in user_input.items() if value]
            if not set(selected_measurands).issubset(set(MEASURANDS)):
                errors["base"] = "no_measurands_selected"
                return self.async_show_form(
                    step_id="measurands",
                    data_schema=STEP_USER_MEASURANDS_SCHEMA,
                    errors=errors,
                )
            else:
                self._measurands = ",".join(selected_measurands)
                self._data[CONF_CPIDS][-1][self._cp_id][CONF_MONITORED_VARIABLES] = (
                    self._measurands
                )

                # With autoconfig off, the cpid was validated a step earlier and
                # nothing has been written yet, so another flow could have taken
                # it in the meantime. Re-check immediately before persisting:
                # there is no await between this and async_update_entry, so on
                # the single-threaded event loop nothing can slip in between.
                pending_cpid = self._data[CONF_CPIDS][-1][self._cp_id][CONF_CPID]
                if pending_cpid in self._other_cpids_in_use():
                    errors["base"] = "duplicate_cpid"
                    return self.async_show_form(
                        step_id="measurands",
                        data_schema=STEP_USER_MEASURANDS_SCHEMA,
                        errors=errors,
                    )

                self.hass.config_entries.async_update_entry(
                    self._entry, data=self._data
                )
                return self.async_abort(reason="Added/Updated charge point")

        return self.async_show_form(
            step_id="measurands",
            data_schema=STEP_USER_MEASURANDS_SCHEMA,
            errors=errors,
        )


class OCPPOptionsFlow(OptionsFlow):
    """Edit an already-configured central system or charge point.

    The initial charger form (async_step_cp_user) is reachable only from
    integration discovery, which aborts for a charger that is already
    configured - so without this flow every per-charger setting was
    write-once (#2047). cpid stays read-only here: entity unique_ids
    derive from it, so changing it would orphan every existing entity.
    """

    def __init__(self) -> None:
        """Initialize."""
        self._cp_id: str = ""
        self._settings: dict[str, Any] = {}
        self._auth_manager: AuthorizationManager | None = None
        self._auth_user_id: str = ""
        self._auth_credential_id: str = ""
        self._auth_pending_id: str = ""
        self._auth_enrollment_cp_id: str = ""
        self._auth_enrollment_label: str = ""
        self._auth_enrollment_task: asyncio.Task[EnrollmentResult] | None = None
        self._auth_enrollment_result: EnrollmentResult | None = None

    async def _get_auth_manager(self) -> AuthorizationManager:
        """Return the loaded manager belonging to this options flow."""
        if self._auth_manager is not None:
            return self._auth_manager
        central = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if central is not None:
            self._auth_manager = central.authorization
        else:
            self._auth_manager = AuthorizationManager(self.hass, self.config_entry)
            await self._auth_manager.async_load()
        return self._auth_manager

    def _loaded_central_system(self):
        """Return the loaded central system, if available."""
        return self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)

    def _charge_points(self) -> dict[str, dict[str, Any]]:
        """Map cp_id to its stored settings for this entry."""
        points: dict[str, dict[str, Any]] = {}
        for item in self.config_entry.data.get(CONF_CPIDS, []):
            for cp_id, settings in item.items():
                points[cp_id] = settings
        return points

    def _server_schema(self) -> vol.Schema:
        """Build the editable central-system schema from stored values."""
        return _central_system_schema(
            self.config_entry.data,
            include_csid=False,
        )

    def _port_in_use(self, port: int) -> bool:
        """Return whether another OCPP entry already listens on this port."""
        return any(
            entry.entry_id != self.config_entry.entry_id
            and entry.data.get(CONF_PORT) == port
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )

    def _finalize(self) -> ConfigFlowResult:
        """Overlay the edited fields onto the charge point and write it back.

        The overlay reads the entry as it is now, not as it was when the
        first form was submitted: while the user sits on the measurands
        form, a reconnecting charger's post_connect can update the entry
        (connector count, detected measurands), and writing back a snapshot
        taken earlier would erase that. Only the fields the user actually
        edited are replaced.
        """
        cpids = [
            {
                cp_id: (
                    {**stored, **self._settings} if cp_id == self._cp_id else stored
                )
                for cp_id, stored in item.items()
            }
            for item in self.config_entry.data.get(CONF_CPIDS, [])
        ]
        # Updating the entry already triggers a reload via the
        # add_update_listener(async_reload_entry) registered in
        # async_setup_entry - the same single-reload rule the reconfigure
        # step follows. The create_entry below writes entry.options, which
        # stays {} and therefore fires nothing on top of it.
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_CPIDS: cpids},
        )
        return self.async_create_entry(data={})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick central, charger, or authorization settings to edit."""
        points = self._charge_points()

        if user_input is not None:
            target = user_input[OPTIONS_TARGET]
            if target == OPTIONS_TARGET_CENTRAL_SYSTEM:
                return await self.async_step_server_settings()
            if target == OPTIONS_TARGET_AUTHORIZATION:
                return await self.async_step_authorization()
            self._cp_id = target
            return await self.async_step_cp_settings()

        targets = {
            OPTIONS_TARGET_CENTRAL_SYSTEM: (
                f"Central system ({self.config_entry.data[CONF_CSID]})"
            ),
            OPTIONS_TARGET_AUTHORIZATION: "Authorization and RFID cards",
            **{
                cp_id: f"Charger {settings[CONF_CPID]} ({cp_id})"
                for cp_id, settings in sorted(points.items())
            },
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(OPTIONS_TARGET): vol.In(targets)}),
        )

    async def async_step_server_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the listener settings of the central system."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if self._port_in_use(user_input[CONF_PORT]):
                errors[CONF_PORT] = "port_in_use"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, **user_input},
                )
                return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="server_settings",
            data_schema=self._server_schema(),
            errors=errors,
            description_placeholders={
                "csid": self.config_entry.data.get(CONF_CSID, DEFAULT_CSID)
            },
        )

    async def async_step_authorization(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show authorization management actions."""
        manager = await self._get_auth_manager()
        menu_options = ["auth_settings", "auth_add_user"]
        if manager.users:
            menu_options.append("auth_select_user")
        if manager.pending_credentials:
            menu_options.append("auth_select_pending")
        menu_options.append("auth_finish")
        return self.async_show_menu(step_id="authorization", menu_options=menu_options)

    async def async_step_auth_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish authorization management without reloading OCPP."""
        return self.async_create_entry(data={})

    async def async_step_auth_back(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Return to the authorization menu."""
        return await self.async_step_authorization()

    async def async_step_auth_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the policy applied to unknown credentials."""
        manager = await self._get_auth_manager()
        if user_input is not None:
            policy_changed = (
                manager.registered_only != user_input[CONF_AUTHORIZATION_REQUIRED]
            )
            await manager.async_set_registered_only(
                user_input[CONF_AUTHORIZATION_REQUIRED]
            )
            if policy_changed:
                await self._async_clear_authorization_caches()
            return await self.async_step_authorization()
        return self.async_show_form(
            step_id="auth_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTHORIZATION_REQUIRED,
                        default=manager.registered_only,
                    ): bool
                }
            ),
        )

    async def async_step_auth_add_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create an authorization user."""
        manager = await self._get_auth_manager()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._auth_user_id = await manager.async_add_user(
                    user_input[CONF_NAME], user_input[AUTH_ENABLED]
                )
            except DuplicateUserNameError:
                errors[CONF_NAME] = "duplicate_user_name"
            else:
                return await self.async_step_auth_user()
        return self.async_show_form(
            step_id="auth_add_user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): cv.string,
                    vol.Required(AUTH_ENABLED, default=True): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_auth_select_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a user to manage."""
        manager = await self._get_auth_manager()
        users = manager.users
        if not users:
            return await self.async_step_authorization()
        if user_input is not None:
            self._auth_user_id = user_input[AUTH_USER_ID]
            return await self.async_step_auth_user()
        choices = {user_id: user["name"] for user_id, user in sorted(users.items())}
        return self.async_show_form(
            step_id="auth_select_user",
            data_schema=vol.Schema({vol.Required(AUTH_USER_ID): vol.In(choices)}),
        )

    async def async_step_auth_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show actions for the selected user."""
        manager = await self._get_auth_manager()
        user = manager.users.get(self._auth_user_id)
        if user is None:
            return await self.async_step_authorization()
        menu_options = ["auth_edit_user", "auth_learn_card"]
        if user["credentials"]:
            menu_options.append("auth_select_card")
        menu_options.extend(["auth_delete_user", "auth_back"])
        return self.async_show_menu(
            step_id="auth_user",
            menu_options=menu_options,
            description_placeholders={"user": user["name"]},
        )

    async def async_step_auth_edit_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected user."""
        manager = await self._get_auth_manager()
        user = manager.users.get(self._auth_user_id)
        if user is None:
            return await self.async_step_authorization()
        errors: dict[str, str] = {}
        if user_input is not None:
            enabled_changed = user["enabled"] != user_input[AUTH_ENABLED]
            try:
                await manager.async_update_user(
                    self._auth_user_id,
                    user_input[CONF_NAME],
                    user_input[AUTH_ENABLED],
                )
            except DuplicateUserNameError:
                errors[CONF_NAME] = "duplicate_user_name"
            else:
                if enabled_changed:
                    await self._async_clear_authorization_caches()
                return await self.async_step_auth_user()
        return self.async_show_form(
            step_id="auth_edit_user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=user["name"]): cv.string,
                    vol.Required(AUTH_ENABLED, default=user["enabled"]): bool,
                }
            ),
            errors=errors,
            description_placeholders={"user": user["name"]},
        )

    async def async_step_auth_delete_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete a user only after explicit confirmation."""
        manager = await self._get_auth_manager()
        user = manager.users.get(self._auth_user_id)
        if user is None:
            return await self.async_step_authorization()
        if user_input is not None:
            if user_input[AUTH_CONFIRM]:
                await manager.async_delete_user(self._auth_user_id)
                if user["credentials"]:
                    await self._async_clear_authorization_caches()
                self._auth_user_id = ""
                return await self.async_step_authorization()
            return await self.async_step_auth_user()
        return self.async_show_form(
            step_id="auth_delete_user",
            data_schema=vol.Schema({vol.Required(AUTH_CONFIRM, default=False): bool}),
            description_placeholders={"user": user["name"]},
        )

    async def async_step_auth_learn_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start an RFID enrollment session for the selected user."""
        manager = await self._get_auth_manager()
        points = self._charge_points()
        errors: dict[str, str] = {}
        if not points:
            return self.async_show_form(
                step_id="auth_learn_card",
                data_schema=vol.Schema({}),
                errors={"base": "no_charge_points"},
            )
        if user_input is not None:
            self._auth_enrollment_cp_id = user_input[AUTH_CHARGE_POINT]
            self._auth_enrollment_label = user_input.get(AUTH_LABEL, "")
            try:
                enrollment = manager.start_enrollment(self._auth_enrollment_cp_id)
            except EnrollmentInProgressError:
                errors["base"] = "rfid_enrollment_in_progress"
            else:

                async def _wait_for_card() -> EnrollmentResult:
                    return await enrollment

                self._auth_enrollment_task = self.hass.async_create_task(
                    _wait_for_card()
                )
                return await self.async_step_auth_wait_for_card()

        choices = {
            cp_id: f"{settings[CONF_CPID]} ({cp_id})"
            for cp_id, settings in sorted(points.items())
        }
        return self.async_show_form(
            step_id="auth_learn_card",
            data_schema=vol.Schema(
                {
                    vol.Required(AUTH_CHARGE_POINT): vol.In(choices),
                    vol.Optional(AUTH_LABEL, default=""): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_auth_wait_for_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wait until the charger reports the next RFID token."""
        task = self._auth_enrollment_task
        if task is None:
            return await self.async_step_auth_user()
        if not task.done():
            return self.async_show_progress(
                step_id="auth_wait_for_card",
                progress_action="auth_wait_for_card",
                progress_task=task,
                description_placeholders={
                    "charger": self._auth_enrollment_cp_id,
                    "seconds": "60",
                },
            )
        try:
            self._auth_enrollment_result = task.result()
        except (TimeoutError, asyncio.CancelledError):
            self._auth_enrollment_task = None
            return self.async_show_progress_done(next_step_id="auth_enrollment_timeout")
        self._auth_enrollment_task = None
        return self.async_show_progress_done(next_step_id="auth_confirm_card")

    async def async_step_auth_enrollment_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Report an enrollment timeout and return to the user menu."""
        if user_input is not None:
            return await self.async_step_auth_user()
        return self.async_show_form(
            step_id="auth_enrollment_timeout", data_schema=vol.Schema({})
        )

    async def _async_clear_authorization_caches(self) -> None:
        """Best-effort removal of stale authorization responses from chargers."""
        central = self._loaded_central_system()
        if central is None:
            return

        async def _clear(cp_id: str) -> None:
            try:
                apply_policy = getattr(central, "apply_authorization_policy", None)
                if apply_policy is not None:
                    await asyncio.wait_for(apply_policy(cp_id), timeout=20)
                await asyncio.wait_for(
                    central.clear_authorization_cache(cp_id), timeout=10
                )
            except TimeoutError:
                return

        await asyncio.gather(*(_clear(cp_id) for cp_id in central.charge_points))

    async def async_step_auth_confirm_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm and persist a captured RFID credential."""
        manager = await self._get_auth_manager()
        result = self._auth_enrollment_result
        users = manager.users
        user = users.get(self._auth_user_id)
        if result is None or user is None:
            return await self.async_step_authorization()

        assigned_user = users.get(result.assigned_user_id or "")
        assigned_name = assigned_user["name"] if assigned_user else ""
        transfer_required = bool(
            result.assigned_user_id and result.assigned_user_id != self._auth_user_id
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_assign_token(
                    self._auth_user_id,
                    result.token,
                    label=user_input[AUTH_LABEL],
                    enabled=user_input[AUTH_ENABLED],
                    authorization_status=user_input[CONF_AUTH_STATUS],
                    transfer=user_input.get(AUTH_TRANSFER, False),
                )
            except CredentialAlreadyAssignedError:
                errors["base"] = "credential_already_assigned"
            else:
                await self._async_clear_authorization_caches()
                self._auth_enrollment_result = None
                return await self.async_step_auth_user()

        fields: dict[Any, Any] = {
            vol.Required(AUTH_LABEL, default=self._auth_enrollment_label): cv.string,
            vol.Required(AUTH_ENABLED, default=True): bool,
            vol.Required(
                CONF_AUTH_STATUS,
                default=AuthorizationStatus.accepted.value,
            ): vol.In(AUTHORIZATION_STATUSES),
        }
        if transfer_required:
            fields[vol.Required(AUTH_TRANSFER, default=False)] = bool
        return self.async_show_form(
            step_id="auth_confirm_card",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "card": mask_token(result.token),
                "user": user["name"],
                "assigned_user": assigned_name,
            },
        )

    async def async_step_auth_select_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select one credential belonging to the active user."""
        manager = await self._get_auth_manager()
        user = manager.users.get(self._auth_user_id)
        if user is None or not user["credentials"]:
            return await self.async_step_auth_user()
        if user_input is not None:
            self._auth_credential_id = user_input[AUTH_CREDENTIAL_ID]
            return await self.async_step_auth_card()
        choices = {
            credential["id"]: (credential["label"] or mask_token(credential["token"]))
            for credential in user["credentials"]
        }
        return self.async_show_form(
            step_id="auth_select_card",
            data_schema=vol.Schema({vol.Required(AUTH_CREDENTIAL_ID): vol.In(choices)}),
        )

    async def async_step_auth_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show actions for a selected credential."""
        credential = self._selected_credential()
        if credential is None:
            return await self.async_step_auth_user()
        return self.async_show_menu(
            step_id="auth_card",
            menu_options=["auth_edit_card", "auth_delete_card", "auth_user"],
            description_placeholders={
                "card": credential["label"] or mask_token(credential["token"])
            },
        )

    def _selected_credential(self) -> dict[str, Any] | None:
        """Return the currently selected credential from a fresh snapshot."""
        if self._auth_manager is None:
            return None
        user = self._auth_manager.users.get(self._auth_user_id)
        if user is None:
            return None
        return next(
            (
                credential
                for credential in user["credentials"]
                if credential["id"] == self._auth_credential_id
            ),
            None,
        )

    async def async_step_auth_edit_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a credential."""
        manager = await self._get_auth_manager()
        credential = self._selected_credential()
        if credential is None:
            return await self.async_step_auth_user()
        if user_input is not None:
            authorization_changed = (
                credential["enabled"] != user_input[AUTH_ENABLED]
                or credential["authorization_status"] != user_input[CONF_AUTH_STATUS]
            )
            await manager.async_update_credential(
                self._auth_credential_id,
                label=user_input[AUTH_LABEL],
                enabled=user_input[AUTH_ENABLED],
                authorization_status=user_input[CONF_AUTH_STATUS],
            )
            if authorization_changed:
                await self._async_clear_authorization_caches()
            return await self.async_step_auth_card()
        return self.async_show_form(
            step_id="auth_edit_card",
            data_schema=vol.Schema(
                {
                    vol.Required(AUTH_LABEL, default=credential["label"]): cv.string,
                    vol.Required(AUTH_ENABLED, default=credential["enabled"]): bool,
                    vol.Required(
                        CONF_AUTH_STATUS,
                        default=credential["authorization_status"],
                    ): vol.In(AUTHORIZATION_STATUSES),
                }
            ),
            description_placeholders={"card": mask_token(credential["token"])},
        )

    async def async_step_auth_delete_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete a credential after confirmation."""
        manager = await self._get_auth_manager()
        credential = self._selected_credential()
        if credential is None:
            return await self.async_step_auth_user()
        if user_input is not None:
            if user_input[AUTH_CONFIRM]:
                await manager.async_delete_credential(self._auth_credential_id)
                await self._async_clear_authorization_caches()
                self._auth_credential_id = ""
                return await self.async_step_auth_user()
            return await self.async_step_auth_card()
        return self.async_show_form(
            step_id="auth_delete_card",
            data_schema=vol.Schema({vol.Required(AUTH_CONFIRM, default=False): bool}),
            description_placeholders={"card": mask_token(credential["token"])},
        )

    async def async_step_auth_select_pending(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select an unassigned RFID scan."""
        manager = await self._get_auth_manager()
        pending = manager.pending_credentials
        if not pending:
            return await self.async_step_authorization()
        if user_input is not None:
            self._auth_pending_id = user_input[AUTH_PENDING_ID]
            return await self.async_step_auth_pending()
        choices = {
            item["id"]: f"{mask_token(item['token'])} ({item['cp_id']})"
            for item in pending
        }
        return self.async_show_form(
            step_id="auth_select_pending",
            data_schema=vol.Schema({vol.Required(AUTH_PENDING_ID): vol.In(choices)}),
        )

    def _selected_pending(self) -> dict[str, Any] | None:
        """Return the selected pending scan from a fresh snapshot."""
        if self._auth_manager is None:
            return None
        return next(
            (
                item
                for item in self._auth_manager.pending_credentials
                if item["id"] == self._auth_pending_id
            ),
            None,
        )

    async def async_step_auth_pending(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show actions for an unassigned RFID scan."""
        manager = await self._get_auth_manager()
        pending = self._selected_pending()
        if pending is None:
            return await self.async_step_authorization()
        menu_options = ["auth_discard_pending", "auth_back"]
        if manager.users:
            menu_options.insert(0, "auth_assign_pending")
        return self.async_show_menu(
            step_id="auth_pending",
            menu_options=menu_options,
            description_placeholders={
                "card": mask_token(pending["token"]),
                "charger": pending["cp_id"],
            },
        )

    async def async_step_auth_assign_pending(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Assign an unassigned scan to a user."""
        manager = await self._get_auth_manager()
        pending = self._selected_pending()
        users = manager.users
        if pending is None or not users:
            return await self.async_step_authorization()
        if user_input is not None:
            await manager.async_assign_pending(
                self._auth_pending_id,
                user_input[AUTH_USER_ID],
                label=user_input[AUTH_LABEL],
            )
            await self._async_clear_authorization_caches()
            self._auth_pending_id = ""
            return await self.async_step_authorization()
        choices = {user_id: user["name"] for user_id, user in users.items()}
        return self.async_show_form(
            step_id="auth_assign_pending",
            data_schema=vol.Schema(
                {
                    vol.Required(AUTH_USER_ID): vol.In(choices),
                    vol.Optional(AUTH_LABEL, default=""): cv.string,
                }
            ),
            description_placeholders={"card": mask_token(pending["token"])},
        )

    async def async_step_auth_discard_pending(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discard a pending scan after confirmation."""
        manager = await self._get_auth_manager()
        pending = self._selected_pending()
        if pending is None:
            return await self.async_step_authorization()
        if user_input is not None:
            if user_input[AUTH_CONFIRM]:
                with contextlib.suppress(UnknownAuthorizationRecordError):
                    await manager.async_discard_pending(self._auth_pending_id)
                self._auth_pending_id = ""
                return await self.async_step_authorization()
            return await self.async_step_auth_pending()
        return self.async_show_form(
            step_id="auth_discard_pending",
            data_schema=vol.Schema({vol.Required(AUTH_CONFIRM, default=False): bool}),
            description_placeholders={"card": mask_token(pending["token"])},
        )

    async def async_step_cp_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the behavioural settings of the chosen charge point."""
        current = self._charge_points()[self._cp_id]

        if user_input is not None:
            # Hold only what the form edited; _finalize overlays it onto the
            # stored record. cpid, the connector count and the measurand
            # list are untouched by construction - in particular the
            # measurand list is NOT reseeded when autoconfig is left on: it
            # holds what detection accepted, and rewriting it here would
            # create sensors for every measurand as a side effect of
            # editing an unrelated setting.
            self._settings = dict(user_input)
            if user_input[CONF_MONITORED_VARIABLES_AUTOCONFIG]:
                return self._finalize()
            return await self.async_step_measurands()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MAX_CURRENT,
                    default=current.get(CONF_MAX_CURRENT, DEFAULT_MAX_CURRENT),
                ): int,
                vol.Required(
                    CONF_MAX_POWER,
                    default=current.get(CONF_MAX_POWER, DEFAULT_MAX_POWER),
                ): int,
                vol.Required(
                    CONF_MONITORED_VARIABLES_AUTOCONFIG,
                    default=current.get(
                        CONF_MONITORED_VARIABLES_AUTOCONFIG,
                        DEFAULT_MONITORED_VARIABLES_AUTOCONFIG,
                    ),
                ): bool,
                vol.Required(
                    CONF_METER_INTERVAL,
                    default=current.get(CONF_METER_INTERVAL, DEFAULT_METER_INTERVAL),
                ): int,
                vol.Required(
                    CONF_IDLE_INTERVAL,
                    default=current.get(CONF_IDLE_INTERVAL, DEFAULT_IDLE_INTERVAL),
                ): vol.All(int, vol.Range(min=0)),
                vol.Optional(
                    CONF_WALLBOX_PROFILE,
                    default=current.get(CONF_WALLBOX_PROFILE, DEFAULT_WALLBOX_PROFILE),
                ): vol.In(WALLBOX_PROFILE_OPTIONS),
                vol.Required(
                    CONF_SKIP_SCHEMA_VALIDATION,
                    default=current.get(
                        CONF_SKIP_SCHEMA_VALIDATION, DEFAULT_SKIP_SCHEMA_VALIDATION
                    ),
                ): bool,
                vol.Required(
                    CONF_FORCE_SMART_CHARGING,
                    default=current.get(
                        CONF_FORCE_SMART_CHARGING, DEFAULT_FORCE_SMART_CHARGING
                    ),
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="cp_settings",
            data_schema=schema,
            description_placeholders={
                "cp_id": self._cp_id,
                "cpid": current.get(CONF_CPID, ""),
            },
        )

    async def async_step_measurands(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select measurands manually, pre-filled with the stored set."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = [m for m, value in user_input.items() if value]
            if selected:
                self._settings[CONF_MONITORED_VARIABLES] = ",".join(selected)
                return self._finalize()
            errors["base"] = "no_measurands_selected"

        current = self._charge_points()[self._cp_id]
        stored = {
            m for m in current.get(CONF_MONITORED_VARIABLES, "").split(",") if m
        } or {DEFAULT_MEASURAND}
        schema = vol.Schema(
            {vol.Required(m, default=(m in stored)): bool for m in MEASURANDS}
        )
        return self.async_show_form(
            step_id="measurands", data_schema=schema, errors=errors
        )
