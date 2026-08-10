<p align="center">
  <img src=".github/assets/ha-ocpp-banner.png" alt="HA OCPP - OCPP server for Home Assistant" width="100%">
</p>

# HA OCPP

[![Open HA OCPP in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alex89rm&repository=ha-ocpp&category=integration)

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
- Exactly one OCPP server listener containing one or more wallboxes.
- Station-wide persistent current or power limits based on the charging-rate
  units advertised by each OCPP 1.6 charger.
- Separate current limits for every connector on multi-connector stations.

The Autel MaxiCharger AC profile includes hardware-verified handling for its
phase-voltage noise floor and for persistent station-wide power limits using
`ChargePointMaxProfile`, `Absolute`, `W`, and connector `0`.

## Installation

1. Open HA OCPP in HACS with the button above. Until the repository is accepted
   into the default HACS catalog, add `https://github.com/alex89rm/ha-ocpp` as a
   custom integration repository first.
2. Install **HA OCPP** and restart Home Assistant.
3. Add the HA OCPP integration from **Settings > Devices & services**.
4. Open **HA OCPP** from the Home Assistant sidebar.

The integration uses the independent `ha_ocpp` Home Assistant domain. The
Python `ocpp` package remains the standards implementation used by the server.

### Upgrading from 0.11.x

Versions through `0.11.x` used the `ocpp` Home Assistant domain. Remove that
integration and its HACS installation, restart Home Assistant, then install and
configure HA OCPP again. Services now use the `ha_ocpp.*` namespace.

## Architecture

See the [documentation index](docs/README.md),
[Architecture](docs/architecture.md), and
[Wallbox profiles](docs/wallbox-profiles.md). Product-specific assets can be
added independently of protocol behavior.

## Project History

HA OCPP began from the MIT-licensed `lbbrhzn/ocpp` Home Assistant integration.
It is now developed and released independently and has no runtime dependency on
that repository. The original copyright and MIT attribution are retained in
[LICENSE](LICENSE).
