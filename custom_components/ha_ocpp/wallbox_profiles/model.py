"""Shared wallbox profile types."""

from __future__ import annotations

import fnmatch
import re

from dataclasses import dataclass

from ocpp.v16.enums import Measurand


def normalize_identity_token(value: str | None) -> str:
    """Return a stable token for vendor and model matching."""
    return re.sub(r"[^a-z0-9*?]", "", str(value or "").casefold())


@dataclass(frozen=True, slots=True)
class WallboxIdentity:
    """Information reported by a charging station at boot."""

    vendor: str = ""
    model: str = ""
    serial: str = ""
    firmware_version: str = ""

    @property
    def normalized_vendor(self) -> str:
        """Return the normalized vendor name."""
        return normalize_identity_token(self.vendor)

    @property
    def normalized_model(self) -> str:
        """Return the normalized model name."""
        return normalize_identity_token(self.model)


@dataclass(frozen=True, slots=True)
class WallboxProfile:
    """Declarative product metadata and bounded protocol quirks."""

    profile_id: str
    display_name: str
    manufacturer: str
    product_family: str
    vendor_patterns: tuple[str, ...] = ()
    model_patterns: tuple[str, ...] = ()
    priority: int = 0
    voltage_noise_floor: float = 0.5
    charging_limit_strategy: str = "standard"
    capability_hints: tuple[str, ...] = ()
    product_image: str | None = None
    hardware_verified: bool = False

    def match_score(self, identity: WallboxIdentity) -> int:
        """Return a deterministic match score or -1 when incompatible."""
        vendor_score = self._pattern_score(
            identity.normalized_vendor, self.vendor_patterns
        )
        if vendor_score < 0:
            return -1
        model_score = self._pattern_score(
            identity.normalized_model, self.model_patterns
        )
        if model_score < 0:
            return -1
        return self.priority + vendor_score + model_score

    @staticmethod
    def _pattern_score(value: str, patterns: tuple[str, ...]) -> int:
        """Score exact matches above wildcard matches."""
        if not patterns:
            return 0
        if not value:
            return -1
        best = -1
        for pattern in patterns:
            normalized = normalize_identity_token(pattern)
            if not fnmatch.fnmatchcase(value, normalized):
                continue
            best = max(best, 80 if value == normalized else 50)
        return best

    def normalize_measurand_value(
        self,
        measurand: str,
        value: float,
        phase: str | None,
    ) -> float:
        """Normalize one value without changing standard OCPP routing."""
        if (
            measurand == Measurand.voltage.value
            and phase is not None
            and abs(value) < self.voltage_noise_floor
        ):
            return 0.0
        return value

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe profile metadata for the dashboard."""
        return {
            "id": self.profile_id,
            "name": self.display_name,
            "manufacturer": self.manufacturer,
            "product_family": self.product_family,
            "charging_limit_strategy": self.charging_limit_strategy,
            "voltage_noise_floor": self.voltage_noise_floor,
            "capability_hints": list(self.capability_hints),
            "product_image": self.product_image,
            "hardware_verified": self.hardware_verified,
        }
