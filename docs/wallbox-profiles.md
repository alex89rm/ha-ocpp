# Wallbox Profiles

A wallbox profile describes product metadata and only the behavior that differs
from, or clarifies, generic OCPP handling.

## Selection

At BootNotification, HA OCPP normalizes the reported vendor and model and asks
the profile registry for the highest-scoring match. Administrators can keep
automatic selection or choose a profile explicitly from the HA OCPP panel and
the integration options.

The generic profile is always the fallback. Adding a vendor profile must never
be required for basic OCPP operation.

## Current Profiles

| Profile | Match | Verified behavior |
| --- | --- | --- |
| Generic OCPP | Fallback | Standards-based behavior and a 0.5 V phase noise floor |
| Autel MaxiCharger | Vendor `Autel*`, model `MaxiCharger*` | 1.0 V phase noise floor; persistent station-wide power limit through `ChargePointMaxProfile` |

## Adding A Product

1. Add a declarative profile module under `custom_components/ha_ocpp/wallbox_profiles/`.
2. Register it in `registry.py` with specific vendor and model patterns.
3. Add matching and normalization tests.
4. Set `hardware_verified=True` only after testing on physical hardware.
5. Put an approved product image in `custom_components/ha_ocpp/frontend/assets/`
   and reference it as `/ha_ocpp_static/assets/<file>`.

Product artwork is presentation metadata. Missing artwork falls back to the
standard EV station icon and must not affect profile matching or OCPP behavior.
