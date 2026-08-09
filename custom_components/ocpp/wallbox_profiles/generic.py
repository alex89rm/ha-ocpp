"""Generic standards-first OCPP wallbox profile."""

from .model import WallboxProfile

GENERIC_PROFILE = WallboxProfile(
    profile_id="generic.ocpp",
    display_name="Generic OCPP wallbox",
    manufacturer="OCPP",
    product_family="Generic charging station",
    voltage_noise_floor=0.5,
)
