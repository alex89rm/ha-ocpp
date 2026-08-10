# Security Policy

## Deployment Boundary

HA OCPP opens an OCPP WebSocket listener on the configured host and port.
Optional TLS encrypts that connection, but the integration does not currently
authenticate charging stations with client certificates or a WebSocket
credential. RFID authorization controls charging transactions and is not
listener authentication.

Use the listener on a trusted network, protect Home Assistant administrator
accounts, and do not expose the OCPP port directly to the public internet.

RFID credentials are stored in Home Assistant private storage. The HA OCPP
panel is administrator-only and can show complete credential values; normal
Home Assistant user-status entities expose masked identifiers.

## Reporting a Vulnerability

Report security issues privately with a
[GitHub security advisory](https://github.com/alex89rm/ha-ocpp/security/advisories/new).
For non-sensitive bugs, use the public
[issue tracker](https://github.com/alex89rm/ha-ocpp/issues).
