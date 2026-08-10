# Wallbox Profiles

A wallbox profile describes a product family and only the behavior that differs
from, or adds evidence to, generic OCPP handling. It is deliberately smaller
than a driver or protocol adapter.

## Selection

When a station sends `BootNotification`, HA OCPP records its vendor, model,
serial number, and firmware version. The profile registry normalizes vendor and
model strings and selects the highest-scoring built-in match. Administrators
can leave automatic selection enabled or store an explicit override from the
HA OCPP panel or integration options.

The Generic OCPP profile is always the fallback. A product-specific profile
must never be required for basic standards-compliant operation.

## Profile Scope

A profile may contain:

- normalized vendor and model matching patterns;
- display name, manufacturer, product family, and product image;
- a measurement noise floor or similarly narrow value normalization;
- capability notes and a named charging-limit strategy;
- a hardware-verification marker backed by a recorded physical test.

A profile must not contain a parallel WebSocket client, duplicate OCPP message
handlers, or its own copies of Home Assistant entities. Protocol differences
belong in the version-specific handlers and should be selected from bounded
profile metadata only when the generic path cannot express the behavior.

Today, the profile object directly controls measurand normalization. Its
charging-limit strategy and capability hints are descriptive dashboard
metadata; the verified Autel limit is sent by the generic OCPP 1.6 handler.

## Current Profiles

| Profile | Match | Current behavior |
| --- | --- | --- |
| Generic OCPP | Fallback | Standards-first behavior; 0.5 V phase noise floor |
| Autel MaxiCharger | Vendor `Autel*`, model `MaxiCharger*` | 1.0 V phase noise floor; product image; hardware-verified persistent station-wide power limit |

The Autel limit was verified on a MaxiCharger AC with
`ChargePointMaxProfile`, `Absolute`, `W`, and connector `0`. A Fluke 87
measurement confirmed that the CP PWM changes in real time and the limit is
still applied to the next transaction. This evidence does not establish a
portable way to read the station's nameplate maximum through OCPP.

## Adding a Product

1. Add a declarative module under
   `custom_components/ha_ocpp/wallbox_profiles/`.
2. Register the profile in `registry.py` with specific vendor and model
   patterns.
3. Add matching, fallback, and normalization tests.
4. Add protocol tests before any profile metadata is allowed to select
   different wire behavior.
5. Set `hardware_verified=True` only after testing on physical hardware and
   documenting exactly what was measured.
6. Put approved product artwork in
   `custom_components/ha_ocpp/frontend/assets/` and reference it below
   `/ha_ocpp_static/assets/`.

Product artwork is presentation metadata. Missing artwork falls back to the
standard EV-station icon and must not affect matching, capabilities, or OCPP
behavior.
