"""Wallbox profile registry for HA OCPP."""

from .model import WallboxIdentity, WallboxProfile
from .registry import (
    AUTO_PROFILE_ID,
    GENERIC_PROFILE_ID,
    get_profile,
    profile_catalog,
    select_profile,
)

__all__ = [
    "AUTO_PROFILE_ID",
    "GENERIC_PROFILE_ID",
    "WallboxIdentity",
    "WallboxProfile",
    "get_profile",
    "profile_catalog",
    "select_profile",
]
