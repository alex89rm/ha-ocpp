# Charging Automation

Home Assistant can adjust an EV charging limit from household demand, solar
surplus, tariff state, or a manually selected operating mode. The automation
must choose the correct scope and unit for the station.

## Prefer the Maximum-Rate Entity

Use the station-wide HA number entity for a persistent safety ceiling:

- `number.<cpid>_maximum_current` when the station advertises `Current`;
- `number.<cpid>_maximum_power` when the station advertises `Power`.

A multi-connector station can also expose
`number.<cpid>_connector_<n>_maximum_current` for connector-specific current
limits. The station-wide ceiling still applies to the combined station.

Calling `number.set_value` keeps automation behavior aligned with the HA OCPP
panel, validates the entity's configured bounds, and rolls the displayed value
back when the station rejects the profile:

```yaml
action:
  - action: number.set_value
    target:
      entity_id: number.garage_wallbox_maximum_power
    data:
      value: "{{ states('sensor.ev_power_budget_w') | float(0) }}"
```

The entity sends a persistent station-wide `ChargePointMaxProfile` to connector
`0`. This is the intended control for a durable maximum and can be updated while
a transaction is active. Avoid sending a new value when the calculated limit
has not materially changed; this reduces OCPP traffic and unnecessary work in
the station.

## Bounds and Minimum Current

The entity maximum is configured by the administrator. It is not discovered
from the station's nameplate rating. Clamp calculated values to the electrical
rating of the station, cable, circuit, and installation.

AC charging commonly has a practical minimum current, often 6 A per active
phase, but the applicable limit depends on the EVSE, vehicle, wiring, and local
rules. A load-balancing automation should pause charging or use the station's
supported minimum instead of repeatedly requesting an invalid value.

Example power budget with an explicit clamp:

```yaml
template:
  - sensor:
      - name: EV power budget W
        unit_of_measurement: W
        state: >-
          {% set spare = states('sensor.grid_spare_power_w') | float(0) %}
          {{ [[spare, 0] | max, 7400] | min | round(0) }}
```

## Update Cadence

Choose a cadence that matches the household meter and avoids oscillation. A
small deadband and a minimum delay between accepted changes are usually more
useful than writing every noisy sample. HA OCPP reports a rejected command to
the automation and restores the last accepted entity value.

The station remains the final authority. An OCPP `Accepted` response confirms
that the profile message was accepted, not that the requested number is a valid
nameplate rating or that the EV can consume it immediately.

## Transaction-Specific Profiles

`ha_ocpp.set_charge_rate` supports an advanced `custom_profile` payload for
cases that genuinely need `TxProfile` or `TxDefaultProfile`. These structures
are OCPP-version-specific and are not portable across every station.

An OCPP 1.6 transaction-specific current example is:

```yaml
action:
  - action: ha_ocpp.set_charge_rate
    data:
      devid: garage_wallbox
      conn_id: 1
      custom_profile: >-
        {
          "transactionId": {{ states('sensor.garage_wallbox_transaction_id') | int }},
          "chargingProfileId": 3001,
          "stackLevel": 1,
          "chargingProfilePurpose": "TxProfile",
          "chargingProfileKind": "Relative",
          "chargingSchedule": {
            "chargingRateUnit": "A",
            "chargingSchedulePeriod": [
              {"startPeriod": 0, "limit": {{ states('sensor.ev_current_budget_a') | float }} }
            ]
          }
        }
```

Use this only after checking the station's supported feature profiles and
charging-rate units. A `TxProfile` applies to the named active transaction;
`TxDefaultProfile` applies to future transactions on the connector. Neither
replaces the station-wide installation ceiling.

HA OCPP does not currently implement `GetCompositeSchedule`, so automations
cannot ask the integration to calculate the final composition of every active
profile.
