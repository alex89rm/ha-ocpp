# HA OCPP

HA OCPP is a Home Assistant-native OCPP server for managing charging stations,
users, RFID credentials, measurements, and charging limits from one operational
panel.

The integration currently supports OCPP 1.6J, OCPP 2.0.1, and experimental
OCPP 2.1 through the Python [`ocpp`](https://github.com/mobilityhouse/ocpp)
package.

## Product Direction

- A complete HA OCPP sidebar panel for wallboxes, users, RFID, and server setup.
- A generic standards-based implementation that works without vendor code.
- Small, declarative wallbox profiles for verified product behavior and bounded
  protocol quirks.
- Automatic profile selection from BootNotification vendor and model metadata,
  with an explicit administrator override.
- Station-wide persistent current or power limits based on the charging-rate
  units advertised by each OCPP 1.6 charger.
- Separate current limits for every connector on multi-connector stations.

The Autel MaxiCharger AC profile includes hardware-verified handling for its
phase-voltage noise floor and for persistent station-wide power limits using
`ChargePointMaxProfile`, `Absolute`, `W`, and connector `0`.

## Installation

1. Add `https://github.com/alex89rm/ha-ocpp` to HACS as a custom integration
   repository.
2. Install **HA OCPP** and restart Home Assistant.
3. Add the HA OCPP integration from **Settings > Devices & services**.
4. Open **HA OCPP** from the Home Assistant sidebar.

The integration domain remains `ocpp` so existing configuration entries,
entities, services, and automations can migrate without being recreated.

## Architecture

See [Architecture](docs/architecture.md) and
[Wallbox profiles](docs/wallbox-profiles.md). Product-specific assets can be
added independently of protocol behavior.

## Project History

HA OCPP began from the MIT-licensed `lbbrhzn/ocpp` Home Assistant integration.
It is now developed and released independently and has no runtime dependency on
that repository. The original copyright and MIT attribution are retained in
[LICENSE](LICENSE).
