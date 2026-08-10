"""Built-in wallbox profile selection."""

from __future__ import annotations

from .autel import AUTEL_MAXICHARGER_PROFILE
from .generic import GENERIC_PROFILE
from .model import WallboxIdentity, WallboxProfile

AUTO_PROFILE_ID = "auto"
GENERIC_PROFILE_ID = GENERIC_PROFILE.profile_id

BUILTIN_PROFILES: tuple[WallboxProfile, ...] = (
    AUTEL_MAXICHARGER_PROFILE,
    GENERIC_PROFILE,
)
_PROFILES_BY_ID = {profile.profile_id: profile for profile in BUILTIN_PROFILES}


def get_profile(profile_id: str) -> WallboxProfile | None:
    """Return a built-in profile by identifier."""
    return _PROFILES_BY_ID.get(profile_id)


def select_profile(
    identity: WallboxIdentity,
    override: str | None = AUTO_PROFILE_ID,
) -> WallboxProfile:
    """Select an explicit profile or the highest-scoring automatic match."""
    if override and override != AUTO_PROFILE_ID:
        return get_profile(override) or GENERIC_PROFILE

    matches = [
        (profile.match_score(identity), profile)
        for profile in BUILTIN_PROFILES
        if profile.profile_id != GENERIC_PROFILE_ID
    ]
    matches = [item for item in matches if item[0] >= 0]
    if not matches:
        return GENERIC_PROFILE
    return max(matches, key=lambda item: (item[0], item[1].profile_id))[1]


def profile_catalog() -> list[dict[str, object]]:
    """Return the available profile metadata for management clients."""
    return [profile.as_dict() for profile in BUILTIN_PROFILES]
