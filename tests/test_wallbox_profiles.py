"""Tests for modular wallbox profile selection."""

from custom_components.ha_ocpp.wallbox_profiles import (
    GENERIC_PROFILE_ID,
    WallboxIdentity,
    get_profile,
    profile_catalog,
    select_profile,
)


def test_autel_maxicharger_is_identified_from_boot_metadata():
    """Autel's real BootNotification strings select its product profile."""
    identity = WallboxIdentity(
        vendor="Autel",
        model="MaxiChargerAC",
        firmware_version="PFA0101|V1.51.00",
    )

    profile = select_profile(identity)

    assert profile.profile_id == "autel.maxicharger"
    assert profile.hardware_verified is True
    assert profile.charging_limit_strategy == "charge_point_max_profile_absolute"
    assert profile.product_image == ("/ha_ocpp_static/assets/autel-maxicharger-ac.png")


def test_profile_matching_normalizes_vendor_and_model_tokens():
    """Harmless punctuation and casing do not break identification."""
    profile = select_profile(
        WallboxIdentity(vendor="AUTEL Energy", model="Maxi-Charger AC")
    )

    assert profile.profile_id == "autel.maxicharger"


def test_unknown_wallbox_uses_generic_profile():
    """An unknown product keeps complete standards-based support."""
    profile = select_profile(WallboxIdentity(vendor="Acme", model="Model X"))

    assert profile.profile_id == GENERIC_PROFILE_ID


def test_manual_profile_override_wins_over_detection():
    """Administrators can force a profile for ambiguous firmware strings."""
    identity = WallboxIdentity(vendor="Acme", model="Unknown")

    assert select_profile(identity, "autel.maxicharger").profile_id == (
        "autel.maxicharger"
    )
    assert select_profile(identity, GENERIC_PROFILE_ID).profile_id == (
        GENERIC_PROFILE_ID
    )


def test_autel_profile_removes_inactive_phase_voltage_noise():
    """Autel's non-zero inactive phases are normalized before aggregation."""
    profile = get_profile("autel.maxicharger")

    assert profile is not None
    assert profile.normalize_measurand_value("Voltage", 0.05, "L2-N") == 0.0
    assert profile.normalize_measurand_value("Voltage", 243.0, "L1-N") == 243.0


def test_profile_catalog_is_safe_for_frontend_clients():
    """The dashboard catalog contains metadata but no matching internals."""
    catalog = profile_catalog()

    assert {item["id"] for item in catalog} == {
        GENERIC_PROFILE_ID,
        "autel.maxicharger",
    }
    assert all("vendor_patterns" not in item for item in catalog)
