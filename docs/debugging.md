# Debugging

## Enable Logs

Add the integration logger to Home Assistant's `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ha_ocpp: debug
```

Restart Home Assistant, reproduce the problem, and open **Settings > System >
Logs**. Search for `ha_ocpp`, the station's OCPP identity, or the negotiated
subprotocol such as `ocpp1.6`.

For WebSocket handshake failures, temporarily add:

```yaml
logger:
  default: info
  logs:
    custom_components.ha_ocpp: debug
    websockets.server: debug
```

Disable verbose logging after diagnosis. Review logs before sharing them:
station serial numbers, network addresses, transaction identifiers, and RFID
values may be sensitive.

## Connection Checklist

1. Confirm the HA OCPP server device reports that its listener is running.
2. Confirm the station URL uses the configured HA host and port.
3. Confirm the final WebSocket path is a stable charge-point identity, for
   example `/garage_wallbox`.
4. Confirm the station offers a supported subprotocol. A server pinned to OCPP
   2.0.1 will reject a station that offers only `ocpp1.6` or no subprotocol.
5. Check that another process or HA OCPP entry is not already using the port.
6. For TLS, verify that Home Assistant can read both certificate paths and that
   the station trusts the certificate chain.

An unknown path starts an integration-discovery flow. Complete that flow before
expecting entities to become available.

## Measurement Checklist

- Confirm the measurand is enabled in the station settings.
- Check whether the station accepted `MeterValueSampleInterval` and
  `ClockAlignedDataInterval`.
- For idle refresh, the OCPP 1.6 station must support `RemoteTrigger`, accept a
  `MeterValues` trigger, and then send a fresh message.
- A retained value means no newer measurement replaced it; it is not evidence
  that the physical quantity is still present.
- Per-phase voltage uses the active wallbox profile's noise floor before
  averaging.

## Charging-Limit Checklist

- Smart Charging must be advertised or explicitly forced for known broken
  firmware.
- The station must advertise the entity's unit in
  `ChargingScheduleAllowedChargingRateUnit`.
- The configured HA maximum is a local safety bound, not a value read from the
  station.
- A rejected request restores the entity's last accepted value and raises a
  Home Assistant error.
- `ha_ocpp.clear_profile` removes charging profiles where the station supports
  it; use it carefully because it can also remove a required safety ceiling.

## Missing Connector Entities

Connector-specific entities are created from the connector count stored after
station discovery. Current versions clamp an invalid count to at least one and
update it after a successful connection. Reconnect the station and reload the
integration if a firmware inventory initially reported the wrong count.

For direct inspection in the Home Assistant Terminal add-on, the integration's
config-entry domain is `ha_ocpp`:

```bash
python3 -c "import json; d=json.load(open('/config/.storage/core.config_entries')); print([e['data'] for e in d['data']['entries'] if e['domain']=='ha_ocpp'])"
```

Do not edit `.storage` files while Home Assistant is running. Include a redacted
config-entry summary and the relevant log window when opening an issue.
