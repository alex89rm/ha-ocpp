# User Guide

Start with [Installation](installation.md), then use the **HA OCPP** sidebar
panel for day-to-day administration. Standard Home Assistant entities remain
available for dashboards, scripts, and automations.

## Server and Station Model

Each HA OCPP integration entry owns an OCPP central-system listener. The server
device contains listener diagnostics and authorization-user sensors. Charging
stations connected to that listener are separate child devices; a station with
multiple outlets also has one child device per connector.

Use one central-system entry for the current supported deployment. Although the
configuration model and panel can represent listeners on different ports, the
domain-level Home Assistant services are not yet routed safely across multiple
loaded entries.

The identity in the station's WebSocket path is its OCPP charge-point identity.
During discovery, HA OCPP also asks for a lowercase Home Assistant identifier
(`cpid`). This second value is the stable base used by entity IDs and must be
unique across all HA OCPP entries.

## Management Panel

The sidebar panel has these operational areas:

- **Overview** shows the server state and connected wallboxes.
- **Wallboxes** shows live status, measurements, connector actions, limits,
  profile selection, and measurement intervals.
- **Users and RFID** manages the access policy, users, cards, and enrollment.
- **Server** changes listener and WebSocket settings.

Panel commands use an administrator-only Home Assistant WebSocket API. Server
or station setting changes update the owning config entry and reload it when
Home Assistant applies the entry update. Live controls call the same backend
objects used by HA entities.

## Measurements and Intervals

HA OCPP creates sensors only from the station configuration and capabilities it
can discover. Unsupported measurands may remain unknown. Disable automatic
measurand detection for firmware that incorrectly accepts every proposed value,
then select only the measurands the station actually implements.

**Meter interval** configures the active transaction sampling interval. **Idle
interval** configures clock-aligned data and, for OCPP 1.6 stations with
`RemoteTrigger`, also schedules a `MeterValues` request while no transaction is
active. A request is also attempted shortly after a transaction stops.

The station is still the source of truth. A station may reject an interval,
round it, treat the key as read-only, or accept `TriggerMessage` without sending
fresh measurements. HA OCPP cannot synthesize a voltage reading that the
station did not report.

Per-phase voltage aggregation ignores values below the active wallbox profile's
noise floor. The generic floor is 0.5 V; the hardware-verified Autel
MaxiCharger profile uses 1.0 V so inactive phases reported near zero do not
reduce the displayed average.

## Charging-Rate Controls

For an OCPP 1.6 station, HA OCPP reads the allowed charging-rate units after
connection:

- `Current` exposes a station-wide **Maximum Current** entity.
- `Power` exposes a station-wide **Maximum Power** entity.
- both advertised units expose both station-wide entities.

These entities send a persistent station-wide `ChargePointMaxProfile` to
connector `0`. They are suitable as the upper bound used by domestic load
balancing and apply independently of the current transaction. The displayed
value is the last value HA OCPP knows the station accepted, restored across an
HA restart when possible. The current implementation does not use
`GetCompositeSchedule` and does not read the active profile back from the
station.

The maximum value of each slider is an administrator-configured safety bound,
not a discovered electrical rating. OCPP 1.6 reports whether `A` or `W` can be
used but has no generic nameplate-capacity key. A station returning `Accepted`
for 13 kW does not prove that a 7.4 kW unit can physically deliver 13 kW. Set
the configured maximum to the lower of the station, cable, and circuit ratings.

For stations with more than one connector, HA OCPP also creates a separate
**Maximum Current** entity on every connector child device. Connector controls
remain connector-scoped and do not remove or widen the station-wide ceiling.

The Autel MaxiCharger AC power path has been physically verified with
`ChargePointMaxProfile`, `Absolute`, `W`, and connector `0`: changing the value
altered CP PWM in real time and the limit remained in force for the next
transaction.

See [Charging Automation](Charge_automation.md) for examples and the distinction
between station-wide and transaction-specific profiles.

## Connector Status and Actions

For OCPP 1.6, connector status can include:

- **Available**: the connector is free according to the station.
- **Preparing**: authorization, cable handling, or the EV handshake is in
  progress.
- **Charging**: energy is being delivered.
- **SuspendedEV**: the EV has paused energy transfer.
- **SuspendedEVSE**: the station has paused energy transfer.
- **Finishing**: the transaction stopped but the connector has not returned to
  its idle state.
- **Reserved**: the connector is reserved.
- **Unavailable**: it was made inoperative or is temporarily unusable.
- **Faulted**: a fault prevents operation.

OCPP 2.x separates connector occupancy from transaction charging state. HA OCPP
normalizes those messages to the common status vocabulary used by its entities
and panel.

The **Start** action is a remote-start request, not a cable-presence detector.
On some stations it preauthorizes a future transaction and may be accepted
while no EV is attached. Only subsequent status messages from the station can
confirm `Preparing` or `Charging`; HA OCPP must not label a vehicle as connected
merely because a remote-start command was accepted.

**Stop** requests termination of the active transaction. **Unlock** asks the
station to release a connector lock; it is useful only for stations with a
controllable cable lock and may legitimately be rejected on a socket or state
that cannot be unlocked. **Availability** changes whether the station or one
connector is operative and may be scheduled until an active transaction ends.

## Users and RFID

HA OCPP stores a user name, enabled state, and zero or more RFID credentials.
Each credential has its complete token, a user-facing label, enabled state, and
OCPP authorization status. The label can describe the card, vehicle, or any
other useful association; it is also used to identify an active session in the
user sensor.

Unknown credentials are accepted by default for backwards compatibility.
Enable **Allow only registered credentials** after adding the users and cards
that should be allowed to charge.

To enroll a card:

1. Select **Read RFID** in the panel or press the station's **Learn RFID**
   configuration button.
2. Choose the connected station and start the 60-second enrollment window.
3. Present the card once.
4. Assign the captured credential to a user and add an optional label.

The learning scan is deliberately rejected and cannot start charging. A card
can belong to only one user. Policy and card changes ask connected stations to
apply the central policy and clear their authorization caches where supported.
Station-side offline authorization can still affect behavior while disconnected.

The admin panel can show complete RFID values because its WebSocket commands
require a Home Assistant administrator. The authorization-user sensor attached
to the server device has state `disabled`, `idle`, or `charging` and exposes
only masked card identifiers in attributes. Its active-session attributes link
the user and card label to the charging station, connector, and transaction.

## Wallbox Profiles

Automatic profile selection uses vendor and model information from
`BootNotification`. A manual profile override is available in station settings.
Leave it on **Automatic** unless diagnosing incorrect product identification.

A profile supplies bounded metadata and normalization, not a separate OCPP
implementation. Unsupported products continue through the Generic OCPP
profile. See [Wallbox Profiles](wallbox-profiles.md) for the extension rules and
hardware evidence.

## Home Assistant Services

Advanced automations can call services in the `ha_ocpp.*` namespace, including:

- `ha_ocpp.set_charge_rate`
- `ha_ocpp.clear_profile`
- `ha_ocpp.trigger_custom_message`
- `ha_ocpp.configure`
- `ha_ocpp.get_configuration`
- `ha_ocpp.data_transfer`
- `ha_ocpp.update_firmware`
- `ha_ocpp.get_diagnostics`

Prefer the station and connector entities for ordinary controls. Service calls
accept a `devid` identifying the target station. A custom charging profile is
an advanced, protocol-version-specific payload and bypasses the safety and unit
selection provided by the dedicated number entities.

## Device-Specific Notes

Firmware behavior varies substantially even when a product advertises OCPP
support. Consult [Supported Devices](supported-devices.md) for reported setup
requirements and known limitations. A historical report is not equivalent to a
current hardware-verified HA OCPP profile.
