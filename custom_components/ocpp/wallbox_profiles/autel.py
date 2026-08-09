"""Autel MaxiCharger hardware profile."""

from .model import WallboxProfile

AUTEL_MAXICHARGER_PROFILE = WallboxProfile(
    profile_id="autel.maxicharger",
    display_name="Autel MaxiCharger",
    manufacturer="Autel",
    product_family="MaxiCharger AC",
    vendor_patterns=("autel*",),
    model_patterns=("maxicharger*",),
    priority=200,
    voltage_noise_floor=1.0,
    charging_limit_strategy="charge_point_max_profile_absolute",
    capability_hints=(
        "station_wide_power_limit",
        "persistent_charge_point_max_profile",
        "rfid",
    ),
    product_image="/ha_ocpp_static/assets/autel-maxicharger-ac.jpg",
    hardware_verified=True,
)
