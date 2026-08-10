"""Authorization registry and RFID enrollment tests."""

import asyncio
from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from ocpp.v16.enums import AuthorizationStatus
from ocpp.v201.enums import (
    IdTokenEnumType,
    TransactionEventEnumType,
    TriggerReasonEnumType,
)
from websockets.protocol import State

from custom_components.ocpp import CONFIG_SCHEMA
from custom_components.ocpp.authorization import (
    AuthorizationManager,
    CredentialAlreadyAssignedError,
    DuplicateUserNameError,
    mask_token,
)
from custom_components.ocpp.chargepoint import ChargePoint as BaseChargePoint
from custom_components.ocpp.const import (
    CONFIG,
    DOMAIN,
    EVENT_TRANSACTION_STARTED,
    CentralSystemSettings,
    ChargerSystemSettings,
)
from custom_components.ocpp.ocppv201 import ChargePoint as ChargePoint201

from .const import MOCK_CONFIG_CS


async def _manager(hass, entry_id="authorization_test") -> AuthorizationManager:
    """Create a clean, storage-backed manager."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_CS,
        entry_id=entry_id,
        title=entry_id,
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {}).setdefault(CONFIG, {})
    manager = AuthorizationManager(hass, entry)
    await manager.async_load()
    return manager


async def test_default_policy_remains_backwards_compatible(hass):
    """Existing installs continue accepting unknown credentials by default."""
    manager = await _manager(hass)

    assert manager.registered_only is False
    assert manager.authorization_status("UNKNOWN") == AuthorizationStatus.accepted.value

    await manager.async_set_registered_only(True)
    assert manager.authorization_status("UNKNOWN") == AuthorizationStatus.invalid.value


async def test_user_and_credential_lifecycle(hass):
    """Users own independently revocable credentials."""
    manager = await _manager(hass)
    await manager.async_set_registered_only(True)
    user_id = await manager.async_add_user("Alessio")
    credential_id = await manager.async_assign_token(
        user_id, "CARD-ONE", label="Key ring"
    )

    assert (
        manager.authorization_status("CARD-ONE") == AuthorizationStatus.accepted.value
    )
    assert manager.user_for_token("CARD-ONE") == (user_id, "Alessio")
    identity = manager.identity_for_token("CARD-ONE")
    assert identity is not None
    assert identity.user_name == "Alessio"
    assert identity.credential_id == credential_id
    assert identity.credential_label == "Key ring"

    await manager.async_update_credential(
        credential_id,
        label="Disabled card",
        enabled=False,
        authorization_status=AuthorizationStatus.accepted.value,
    )
    assert manager.authorization_status("CARD-ONE") == AuthorizationStatus.blocked.value

    await manager.async_update_credential(
        credential_id,
        label="Expired card",
        enabled=True,
        authorization_status=AuthorizationStatus.expired.value,
    )
    assert manager.authorization_status("CARD-ONE") == AuthorizationStatus.expired.value

    await manager.async_delete_credential(credential_id)
    assert manager.authorization_status("CARD-ONE") == AuthorizationStatus.invalid.value


async def test_users_require_unique_display_names(hass):
    """Dynamic pickers remain unambiguous."""
    manager = await _manager(hass)
    await manager.async_add_user("Mario")

    with pytest.raises(DuplicateUserNameError):
        await manager.async_add_user("mario")


async def test_learning_scan_is_rejected_until_assigned(hass):
    """Pairing never opens an authorization window for the scanned card."""
    manager = await _manager(hass)
    user_id = await manager.async_add_user("Alessio")
    enrollment = manager.start_enrollment("AUTEL")

    assert manager.capture_for_enrollment("AUTEL", "NEW-CARD") is True
    result = await enrollment
    assert result.token == "NEW-CARD"
    assert result.pending_id is not None
    assert (
        manager.authorization_status("NEW-CARD", "AUTEL")
        == AuthorizationStatus.invalid.value
    )

    await manager.async_assign_token(user_id, result.token)
    assert manager.pending_credentials == []
    assert (
        manager.authorization_status("NEW-CARD", "AUTEL")
        == AuthorizationStatus.accepted.value
    )


async def test_unassigned_button_scan_stays_invalid_in_allow_all_mode(hass):
    """A generic Learn RFID button cannot accidentally approve a transaction."""
    manager = await _manager(hass)
    enrollment = manager.start_enrollment("AUTEL", notify=False)

    manager.capture_for_enrollment("AUTEL", "PENDING")
    await enrollment

    assert manager.registered_only is False
    assert (
        manager.authorization_status("PENDING", "AUTEL")
        == AuthorizationStatus.invalid.value
    )


async def test_transfer_requires_explicit_confirmation(hass):
    """A scan cannot silently steal a credential from another user."""
    manager = await _manager(hass)
    first = await manager.async_add_user("First")
    second = await manager.async_add_user("Second")
    await manager.async_assign_token(first, "SHARED")

    with pytest.raises(CredentialAlreadyAssignedError):
        await manager.async_assign_token(second, "SHARED")

    await manager.async_assign_token(second, "SHARED", transfer=True)
    assert manager.user_for_token("SHARED") == (second, "Second")
    assert manager.users[first]["credentials"] == []


async def test_registry_persists_without_reloading_the_config_entry(hass):
    """A fresh manager restores users and policy from private storage."""
    manager = await _manager(hass, "persistent_authorization")
    user_id = await manager.async_add_user("Stored user")
    await manager.async_assign_token(user_id, "STORED-CARD")
    await manager.async_set_registered_only(True)

    restored = AuthorizationManager(hass, manager.entry)
    await restored.async_load()

    assert restored.registered_only is True
    assert restored.user_for_token("STORED-CARD") == (user_id, "Stored user")


@pytest.mark.parametrize(
    "authorization_list",
    [
        [
            {
                "id_tag": "LEGACY",
                "name": "Legacy user",
                "authorization_status": "Accepted",
            }
        ],
        {
            "legacy_user": {
                "id_tag": "LEGACY",
                "name": "Legacy user",
                "authorization_status": "Accepted",
            }
        },
    ],
)
async def test_legacy_yaml_is_validated_normalized_and_imported(
    hass, authorization_list
):
    """Both historical list YAML and the old declared mapping remain accepted."""
    validated = CONFIG_SCHEMA(
        {
            DOMAIN: {
                "default_authorization_status": "Invalid",
                "authorization_list": authorization_list,
            }
        }
    )
    assert isinstance(validated[DOMAIN]["authorization_list"], list)

    hass.data.setdefault(DOMAIN, {})[CONFIG] = validated[DOMAIN]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_CS,
        entry_id=f"legacy_{isinstance(authorization_list, dict)}",
        title="legacy",
    )
    entry.add_to_hass(hass)
    manager = AuthorizationManager(hass, entry)
    await manager.async_load()

    assert manager.registered_only is True
    assert manager.authorization_status("LEGACY") == AuthorizationStatus.accepted.value
    assert manager.user_for_token("LEGACY")[1] == "Legacy user"


async def test_enrollment_times_out(hass):
    """An unanswered enrollment releases the charger for another attempt."""
    manager = await _manager(hass)
    enrollment = manager.start_enrollment("AUTEL", timeout=0)
    await asyncio.sleep(0)

    with pytest.raises(TimeoutError):
        await enrollment

    retry = manager.start_enrollment("AUTEL")
    retry.cancel()
    await manager.async_shutdown()


async def test_v201_transaction_event_cannot_bypass_authorization(hass):
    """A station that skips Authorize still receives the registry decision."""
    manager = await _manager(hass, "v201_authorization")
    await manager.async_set_registered_only(True)
    central = CentralSystemSettings(**manager.entry.data)
    charger = ChargerSystemSettings(
        cpid="test_cpid",
        max_current=32,
        idle_interval=60,
        meter_interval=60,
        monitored_variables="",
        monitored_variables_autoconfig=False,
        skip_schema_validation=False,
        force_smart_charging=False,
    )
    connection = SimpleNamespace(
        state=State.CLOSED,
        close=lambda: asyncio.sleep(0),
        subprotocol="ocpp2.0.1",
    )
    charge_point = ChargePoint201(
        "CP_A",
        connection,
        hass,
        manager.entry,
        central,
        charger,
        manager,
    )

    response = charge_point.on_transaction_event(
        event_type=TransactionEventEnumType.started.value,
        timestamp="2026-08-09T12:00:00Z",
        trigger_reason=TriggerReasonEnumType.authorized.value,
        seq_no=0,
        transaction_info={"transaction_id": "tx-1"},
        evse={"id": 1, "connector_id": 1},
        id_token={
            "type": IdTokenEnumType.iso14443.value,
            "id_token": "UNKNOWN-RFID",
        },
    )

    assert response.id_token_info["status"] == AuthorizationStatus.invalid.value


async def test_transaction_start_is_written_to_logbook_and_event(hass, monkeypatch):
    """A registered card identifies its user in HA activity and automations."""
    manager = await _manager(hass, "transaction_activity")
    user_id = await manager.async_add_user("Alessio")
    credential_id = await manager.async_assign_token(user_id, "CARD-ONE", label="A250e")
    entries = []
    events = []
    monkeypatch.setattr(
        "custom_components.ocpp.chargepoint.async_log_entry",
        lambda *args: entries.append(args),
    )
    hass.config.language = "it"
    remove_listener = hass.bus.async_listen(
        EVENT_TRANSACTION_STARTED, lambda event: events.append(event.data)
    )
    charge_point = SimpleNamespace(
        authorization=manager,
        hass=hass,
        id="AUTEL_CP",
        settings=SimpleNamespace(cpid="autel"),
    )

    BaseChargePoint.log_transaction_started(charge_point, "CARD-ONE", 1, 42)
    await hass.async_block_till_done()
    remove_listener()

    assert entries == [
        (
            hass,
            "HA OCPP",
            "Alessio ha avviato la ricarica con la tessera A250e su autel",
            DOMAIN,
        )
    ]
    assert events == [
        {
            "charge_point_id": "AUTEL_CP",
            "cpid": "autel",
            "connector_id": 1,
            "transaction_id": 42,
            "user_id": user_id,
            "user_name": "Alessio",
            "credential_id": credential_id,
            "credential_label": "A250e",
            "credential_display_name": "A250e",
        }
    ]


def test_mask_token_never_exposes_more_than_the_suffix():
    """UI and notifications do not expose complete credential values."""
    assert mask_token("1234567890") == "******7890"
    assert mask_token("1234") == "****"
