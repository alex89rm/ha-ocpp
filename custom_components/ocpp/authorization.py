"""Authorization registry and RFID enrollment for OCPP central systems."""

from __future__ import annotations

import asyncio
import copy
import logging

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send
from ocpp.v16.enums import AuthorizationStatus

from .const import (
    CONF_AUTH_LIST,
    CONF_AUTH_STATUS,
    CONF_DEFAULT_AUTH_STATUS,
    CONF_ID_TAG,
    CONF_NAME,
    CONFIG,
    DASHBOARD_UPDATED,
    DOMAIN,
)

_LOGGER = logging.getLogger(__package__)

STORAGE_VERSION = 1
DEFAULT_ENROLLMENT_TIMEOUT = 60

AUTHORIZATION_STATUSES = tuple(status.value for status in AuthorizationStatus)


class AuthorizationRegistryError(Exception):
    """Base error raised by the authorization registry."""


class EnrollmentInProgressError(AuthorizationRegistryError):
    """An enrollment session is already active for the charger."""


class CredentialAlreadyAssignedError(AuthorizationRegistryError):
    """A credential belongs to another user."""


class DuplicateUserNameError(AuthorizationRegistryError):
    """A user with the requested name already exists."""


class UnknownAuthorizationRecordError(AuthorizationRegistryError):
    """A requested user, credential, or pending scan does not exist."""


@dataclass(frozen=True)
class EnrollmentResult:
    """RFID credential captured during an enrollment session."""

    token: str
    cp_id: str
    assigned_user_id: str | None
    pending_id: str | None


@dataclass
class _EnrollmentSession:
    """An in-memory RFID enrollment session."""

    future: asyncio.Future[EnrollmentResult]
    timeout_handle: asyncio.TimerHandle
    notify: bool
    expires_at: float


def mask_token(token: str) -> str:
    """Mask a credential while retaining enough characters to identify it."""
    if len(token) <= 4:
        return "*" * len(token)
    return f"{'*' * (len(token) - 4)}{token[-4:]}"


class AuthorizationManager:
    """Persist and evaluate authorization credentials for one central system."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize an unloaded authorization manager."""
        self.hass = hass
        self.entry = entry
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry.entry_id}.authorization",
            private=True,
            atomic_writes=True,
        )
        self._data: dict[str, Any] = self._empty_data()
        self._loaded = False
        self._enrollments: dict[str, _EnrollmentSession] = {}
        self._temporarily_blocked: dict[tuple[str, str], float] = {}

    @staticmethod
    def _empty_data() -> dict[str, Any]:
        """Return an empty registry using backwards-compatible authorization."""
        return {
            "default_status": AuthorizationStatus.accepted.value,
            "users": {},
            "pending_credentials": [],
        }

    async def async_load(self) -> None:
        """Load the registry and import legacy YAML on first use."""
        if self._loaded:
            return

        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._data = self._sanitize(stored)
        else:
            self._data = self._empty_data()
            self._import_legacy_yaml()
            await self._async_save()
        self._loaded = True

    def _sanitize(self, stored: dict[str, Any]) -> dict[str, Any]:
        """Accept only the known, serializable parts of a stored registry."""
        default_status = stored.get(
            "default_status", AuthorizationStatus.accepted.value
        )
        if default_status not in AUTHORIZATION_STATUSES:
            default_status = AuthorizationStatus.accepted.value

        users: dict[str, dict[str, Any]] = {}
        for user_id, user in stored.get("users", {}).items():
            if not isinstance(user_id, str) or not isinstance(user, dict):
                continue
            name = str(user.get("name", "")).strip()
            if not name:
                continue
            credentials = []
            for credential in user.get("credentials", []):
                cleaned = self._sanitize_credential(credential)
                if cleaned is not None:
                    credentials.append(cleaned)
            users[user_id] = {
                "name": name,
                "enabled": bool(user.get("enabled", True)),
                "credentials": credentials,
            }

        pending = []
        for item in stored.get("pending_credentials", []):
            if not isinstance(item, dict):
                continue
            token = str(item.get("token", "")).strip()
            cp_id = str(item.get("cp_id", "")).strip()
            if not token or not cp_id:
                continue
            pending.append(
                {
                    "id": str(item.get("id") or uuid4().hex),
                    "token": token,
                    "cp_id": cp_id,
                    "created_at": str(item.get("created_at") or self._now()),
                }
            )

        return {
            "default_status": default_status,
            "users": users,
            "pending_credentials": pending,
        }

    @staticmethod
    def _sanitize_credential(credential: Any) -> dict[str, Any] | None:
        """Return a valid credential record or discard malformed data."""
        if not isinstance(credential, dict):
            return None
        token = str(credential.get("token", "")).strip()
        if not token:
            return None
        status = credential.get(
            "authorization_status", AuthorizationStatus.accepted.value
        )
        if status not in AUTHORIZATION_STATUSES:
            status = AuthorizationStatus.invalid.value
        return {
            "id": str(credential.get("id") or uuid4().hex),
            "token": token,
            "label": str(credential.get("label", "")).strip(),
            "enabled": bool(credential.get("enabled", True)),
            "authorization_status": status,
            "created_at": str(
                credential.get("created_at") or AuthorizationManager._now()
            ),
        }

    def _import_legacy_yaml(self) -> None:
        """Import the historical domain-wide YAML list into this registry."""
        config = self.hass.data.get(DOMAIN, {}).get(CONFIG, {})
        default_status = config.get(
            CONF_DEFAULT_AUTH_STATUS, AuthorizationStatus.accepted.value
        )
        if default_status in AUTHORIZATION_STATUSES:
            self._data["default_status"] = default_status

        auth_list = config.get(CONF_AUTH_LIST, [])
        if isinstance(auth_list, dict):
            auth_list = list(auth_list.values())
        if not isinstance(auth_list, list):
            return

        imported = 0
        for item in auth_list:
            if not isinstance(item, dict):
                continue
            token = str(item.get(CONF_ID_TAG, "")).strip()
            if not token:
                continue
            status = item.get(CONF_AUTH_STATUS, self._data["default_status"])
            if status not in AUTHORIZATION_STATUSES:
                status = self._data["default_status"]
            user_id = uuid4().hex
            self._data["users"][user_id] = {
                "name": str(item.get(CONF_NAME) or f"Card {mask_token(token)}"),
                "enabled": True,
                "credentials": [
                    {
                        "id": uuid4().hex,
                        "token": token,
                        "label": "",
                        "enabled": True,
                        "authorization_status": status,
                        "created_at": self._now(),
                    }
                ],
            }
            imported += 1

        if imported:
            _LOGGER.info(
                "Imported %d legacy authorization credential(s) for central system %s",
                imported,
                self.entry.title,
            )

    @staticmethod
    def _now() -> str:
        """Return a storage-friendly UTC timestamp."""
        return datetime.now(UTC).isoformat()

    async def _async_save(self) -> None:
        """Persist the current registry."""
        await self._store.async_save(copy.deepcopy(self._data))
        async_dispatcher_send(self.hass, DASHBOARD_UPDATED)

    def _delay_save(self) -> None:
        """Schedule persistence from synchronous OCPP handlers."""
        self._store.async_delay_save(lambda: copy.deepcopy(self._data), delay=0)
        async_dispatcher_send(self.hass, DASHBOARD_UPDATED)

    @property
    def registered_only(self) -> bool:
        """Return whether unknown credentials are rejected."""
        return self._data["default_status"] != AuthorizationStatus.accepted.value

    @property
    def users(self) -> dict[str, dict[str, Any]]:
        """Return a defensive copy of users and their credentials."""
        return copy.deepcopy(self._data["users"])

    @property
    def pending_credentials(self) -> list[dict[str, Any]]:
        """Return a defensive copy of unassigned credential scans."""
        return copy.deepcopy(self._data["pending_credentials"])

    @property
    def active_enrollments(self) -> list[dict[str, Any]]:
        """Return active enrollment windows without exposing card data."""
        now = monotonic()
        return [
            {
                "cp_id": cp_id,
                "seconds_remaining": max(0, round(session.expires_at - now)),
            }
            for cp_id, session in self._enrollments.items()
        ]

    async def async_set_registered_only(self, registered_only: bool) -> None:
        """Set the default policy for unknown credentials."""
        self._data["default_status"] = (
            AuthorizationStatus.invalid.value
            if registered_only
            else AuthorizationStatus.accepted.value
        )
        await self._async_save()

    def _find_user_by_name(
        self, name: str, *, exclude_user_id: str | None = None
    ) -> str | None:
        """Find a user using a case-insensitive display-name comparison."""
        wanted = name.casefold()
        for user_id, user in self._data["users"].items():
            if user_id != exclude_user_id and user["name"].casefold() == wanted:
                return user_id
        return None

    async def async_add_user(self, name: str, enabled: bool = True) -> str:
        """Create a user and return its stable identifier."""
        name = name.strip()
        if not name:
            raise ValueError("User name cannot be empty")
        if self._find_user_by_name(name) is not None:
            raise DuplicateUserNameError
        user_id = uuid4().hex
        self._data["users"][user_id] = {
            "name": name,
            "enabled": enabled,
            "credentials": [],
        }
        await self._async_save()
        return user_id

    async def async_update_user(self, user_id: str, name: str, enabled: bool) -> None:
        """Update an existing user."""
        user = self._data["users"].get(user_id)
        if user is None:
            raise UnknownAuthorizationRecordError
        name = name.strip()
        if not name:
            raise ValueError("User name cannot be empty")
        if self._find_user_by_name(name, exclude_user_id=user_id) is not None:
            raise DuplicateUserNameError
        user["name"] = name
        user["enabled"] = enabled
        await self._async_save()

    async def async_delete_user(self, user_id: str) -> None:
        """Delete a user and all credentials assigned to it."""
        if self._data["users"].pop(user_id, None) is None:
            raise UnknownAuthorizationRecordError
        await self._async_save()

    def _find_credential(
        self, token: str
    ) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
        """Return user id, user and credential for a token."""
        for user_id, user in self._data["users"].items():
            for credential in user["credentials"]:
                if credential["token"] == token:
                    return user_id, user, credential
        return None

    def _find_credential_by_id(
        self, credential_id: str
    ) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
        """Return user id, user and credential for a record id."""
        for user_id, user in self._data["users"].items():
            for credential in user["credentials"]:
                if credential["id"] == credential_id:
                    return user_id, user, credential
        return None

    def user_for_token(self, token: str) -> tuple[str, str] | None:
        """Return the assigned user id and display name for a token."""
        match = self._find_credential(token)
        if match is None:
            return None
        user_id, user, _ = match
        return user_id, user["name"]

    def authorization_status(self, token: str, cp_id: str | None = None) -> str:
        """Evaluate a credential without causing side effects."""
        if cp_id is not None:
            blocked_until = self._temporarily_blocked.get((cp_id, token))
            if blocked_until is not None:
                if blocked_until > monotonic():
                    return AuthorizationStatus.invalid.value
                self._temporarily_blocked.pop((cp_id, token), None)

        if any(
            pending["token"] == token for pending in self._data["pending_credentials"]
        ):
            return AuthorizationStatus.invalid.value

        match = self._find_credential(token)
        if match is None:
            return self._data["default_status"]
        _, user, credential = match
        if not user["enabled"] or not credential["enabled"]:
            return AuthorizationStatus.blocked.value
        return credential["authorization_status"]

    async def async_assign_token(
        self,
        user_id: str,
        token: str,
        *,
        label: str = "",
        enabled: bool = True,
        authorization_status: str = AuthorizationStatus.accepted.value,
        transfer: bool = False,
    ) -> str:
        """Assign a token to a user, requiring consent before a transfer."""
        user = self._data["users"].get(user_id)
        if user is None:
            raise UnknownAuthorizationRecordError
        if authorization_status not in AUTHORIZATION_STATUSES:
            raise ValueError("Invalid authorization status")

        match = self._find_credential(token)
        if match is not None:
            current_user_id, current_user, credential = match
            if current_user_id != user_id:
                if not transfer:
                    raise CredentialAlreadyAssignedError
                current_user["credentials"].remove(credential)
                user["credentials"].append(credential)
            credential["label"] = label.strip()
            credential["enabled"] = enabled
            credential["authorization_status"] = authorization_status
            credential_id = credential["id"]
        else:
            credential_id = uuid4().hex
            user["credentials"].append(
                {
                    "id": credential_id,
                    "token": token,
                    "label": label.strip(),
                    "enabled": enabled,
                    "authorization_status": authorization_status,
                    "created_at": self._now(),
                }
            )

        self._data["pending_credentials"] = [
            item for item in self._data["pending_credentials"] if item["token"] != token
        ]
        self._temporarily_blocked = {
            key: expires
            for key, expires in self._temporarily_blocked.items()
            if key[1] != token
        }
        await self._async_save()
        return credential_id

    async def async_assign_pending(
        self,
        pending_id: str,
        user_id: str,
        *,
        label: str = "",
    ) -> tuple[str, str]:
        """Assign a captured, unassigned credential to a user."""
        pending = next(
            (
                item
                for item in self._data["pending_credentials"]
                if item["id"] == pending_id
            ),
            None,
        )
        if pending is None:
            raise UnknownAuthorizationRecordError
        credential_id = await self.async_assign_token(
            user_id,
            pending["token"],
            label=label,
        )
        return credential_id, pending["cp_id"]

    async def async_discard_pending(self, pending_id: str) -> None:
        """Discard an unassigned credential scan."""
        original_length = len(self._data["pending_credentials"])
        self._data["pending_credentials"] = [
            item
            for item in self._data["pending_credentials"]
            if item["id"] != pending_id
        ]
        if len(self._data["pending_credentials"]) == original_length:
            raise UnknownAuthorizationRecordError
        await self._async_save()

    async def async_update_credential(
        self,
        credential_id: str,
        *,
        label: str,
        enabled: bool,
        authorization_status: str,
    ) -> None:
        """Update a credential's display and authorization state."""
        match = self._find_credential_by_id(credential_id)
        if match is None:
            raise UnknownAuthorizationRecordError
        if authorization_status not in AUTHORIZATION_STATUSES:
            raise ValueError("Invalid authorization status")
        _, _, credential = match
        credential["label"] = label.strip()
        credential["enabled"] = enabled
        credential["authorization_status"] = authorization_status
        await self._async_save()

    async def async_delete_credential(self, credential_id: str) -> None:
        """Delete one credential without deleting its user."""
        match = self._find_credential_by_id(credential_id)
        if match is None:
            raise UnknownAuthorizationRecordError
        _, user, credential = match
        user["credentials"].remove(credential)
        await self._async_save()

    def start_enrollment(
        self,
        cp_id: str,
        *,
        timeout: int = DEFAULT_ENROLLMENT_TIMEOUT,
        notify: bool = False,
    ) -> asyncio.Future[EnrollmentResult]:
        """Wait for the next credential presented to a specific charger."""
        if cp_id in self._enrollments:
            raise EnrollmentInProgressError

        loop = asyncio.get_running_loop()
        future: asyncio.Future[EnrollmentResult] = loop.create_future()
        timeout_handle = loop.call_later(timeout, self._expire_enrollment, cp_id)
        self._enrollments[cp_id] = _EnrollmentSession(
            future=future,
            timeout_handle=timeout_handle,
            notify=notify,
            expires_at=monotonic() + timeout,
        )
        async_dispatcher_send(self.hass, DASHBOARD_UPDATED)

        if notify:
            # A device button has no flow waiting on this future. Consume a
            # timeout exception after the persistent notification reports it.
            future.add_done_callback(self._consume_notification_future)
            persistent_notification.async_create(
                self.hass,
                f"Present an RFID card to charger {cp_id} within {timeout} seconds.",
                title="HA OCPP RFID enrollment",
                notification_id=self._notification_id(cp_id),
            )
        return future

    @staticmethod
    def _consume_notification_future(
        future: asyncio.Future[EnrollmentResult],
    ) -> None:
        """Retrieve a button enrollment result to avoid unhandled futures."""
        if not future.cancelled():
            future.exception()

    def _expire_enrollment(self, cp_id: str) -> None:
        """Expire an enrollment session and wake its waiting flow."""
        session = self._enrollments.pop(cp_id, None)
        if session is None:
            return
        if not session.future.done():
            session.future.set_exception(TimeoutError)
        if session.notify:
            persistent_notification.async_create(
                self.hass,
                f"No RFID card was read by charger {cp_id}.",
                title="HA OCPP RFID enrollment timed out",
                notification_id=self._notification_id(cp_id),
            )
        async_dispatcher_send(self.hass, DASHBOARD_UPDATED)

    def capture_for_enrollment(self, cp_id: str, token: str) -> bool:
        """Capture a token and return whether normal authorization must be denied."""
        session = self._enrollments.pop(cp_id, None)
        if session is None:
            return False
        session.timeout_handle.cancel()

        match = self._find_credential(token)
        assigned_user_id = match[0] if match is not None else None
        pending_id = None
        if match is None:
            existing_pending = next(
                (
                    item
                    for item in self._data["pending_credentials"]
                    if item["token"] == token
                ),
                None,
            )
            if existing_pending is None:
                pending_id = uuid4().hex
                self._data["pending_credentials"].append(
                    {
                        "id": pending_id,
                        "token": token,
                        "cp_id": cp_id,
                        "created_at": self._now(),
                    }
                )
                self._delay_save()
            else:
                pending_id = existing_pending["id"]

        # The learning tap must never authorize a transaction. Unknown tokens
        # remain denied while pending; known tokens get a short safety block.
        self._temporarily_blocked[(cp_id, token)] = monotonic() + 60
        result = EnrollmentResult(
            token=token,
            cp_id=cp_id,
            assigned_user_id=assigned_user_id,
            pending_id=pending_id,
        )
        if not session.future.done():
            session.future.set_result(result)

        if session.notify:
            assignment = (
                "It is already assigned to a user."
                if assigned_user_id is not None
                else "Open the OCPP authorization settings to assign it to a user."
            )
            persistent_notification.async_create(
                self.hass,
                f"Card {mask_token(token)} was read by charger {cp_id}. {assignment}",
                title="HA OCPP RFID card captured",
                notification_id=self._notification_id(cp_id),
            )
        async_dispatcher_send(self.hass, DASHBOARD_UPDATED)
        return True

    def _notification_id(self, cp_id: str) -> str:
        """Return a stable notification id for one charger's enrollment."""
        return f"{DOMAIN}_rfid_{self.entry.entry_id}_{cp_id}"

    async def async_shutdown(self) -> None:
        """Cancel active enrollment sessions during integration unload."""
        for session in self._enrollments.values():
            session.timeout_handle.cancel()
            if not session.future.done():
                session.future.cancel()
        self._enrollments.clear()
