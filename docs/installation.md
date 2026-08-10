# Installation

HA OCPP is currently installed from its GitHub repository as a custom HACS
integration.

## Install with HACS

1. Install and configure [HACS](https://www.hacs.xyz/docs/use/download/download/)
   if it is not already available.
2. Open HACS, use the menu in the top-right corner, and select
   [**Custom repositories**](https://www.hacs.xyz/docs/faq/custom_repositories/).
3. Add `https://github.com/alex89rm/ha-ocpp` with type **Integration**.
4. Open the new **HA OCPP** repository in HACS and download the latest release.
5. Restart Home Assistant.

HACS installs the runtime below `/config/custom_components/ha_ocpp`. The folder
name is part of the Home Assistant domain and must not be changed.

## Add the Integration

1. Open **Settings > Devices & services**.
2. Select **Add integration**, search for **HA OCPP**, and open it.
3. Configure the central-system listener.

The default host `0.0.0.0` listens on every network interface of the Home
Assistant host. The default OCPP WebSocket port is `9000`. Pin an OCPP version
only when a station negotiates the wrong version; **Auto** advertises all
supported subprotocols in the server's configured order.

After setup, the **HA OCPP** management panel appears in the Home Assistant
sidebar. A central-system device is also created under the integration for
diagnostic and user-status entities.

## TLS

Enable **Secure connection** to serve OCPP over `wss://`, then provide paths to
the certificate chain and private key available to Home Assistant, commonly
below `/ssl`.

TLS encrypts the WebSocket transport. It does not make RFID authorization into
WebSocket client authentication, and HA OCPP does not currently validate a
station client certificate. Keep an unencrypted listener on a trusted local
network and do not expose port `9000` directly to the public internet.

## Connect a Charging Station

Configure the station's central-system URL using the Home Assistant address,
the configured port, and a unique OCPP charge-point identity as the path. For
example:

```text
ws://homeassistant.local:9000/garage_wallbox
```

Use `wss://` when TLS is enabled. Some station interfaces append their serial
number automatically or accept only the server portion of the URL; follow the
manufacturer's OCPP instructions while ensuring the final WebSocket request has
a stable, unique path.

When an unknown identity first connects, HA OCPP starts an integration-discovery
flow. Complete the discovered station's configuration in Home Assistant, then
allow the station to reconnect. Choose a lowercase HA identifier containing
only letters, numbers, and underscores; this identifier becomes the stable base
for its entities.

After connection, HA OCPP detects the connector count, feature profiles,
measurands, and OCPP 1.6 charging-rate units where the station supports those
queries. A station that cannot safely auto-detect measurands can be configured
with automatic detection disabled and an explicit list.

## Multiple Connectors

The charging station is the root device. Connector-specific sensors and
controls are attached to child devices such as `Connector 1` and `Connector 2`.
Station-wide current or power controls remain on the root device. If the
station reports a corrected connector count after setup, reconnect it and
reload the integration so Home Assistant can create the corresponding child
entities.

## Upgrading from the Old Domain

Releases through `0.11.x` used `ocpp` as the Home Assistant domain. HA OCPP now
uses the independent `ha_ocpp` domain, including config entries, devices,
entities, services, storage, and the integration folder.

There is no automatic cross-domain migration. Remove the old integration and
old HACS repository installation, restart Home Assistant, install HA OCPP, and
configure the server and stations again. Automations must use the
`ha_ocpp.*` service namespace and the newly created entity IDs.
