# HA OCPP Architecture

HA OCPP is a Home Assistant integration and an OCPP central system. The generic
protocol implementation, product-specific behavior, Home Assistant entities,
and the management panel are intentionally separate layers.

## Naming Boundaries

- `ha_ocpp` is the Home Assistant integration domain, the service namespace,
  the config-entry domain, and the storage namespace.
- `HA OCPP` is the product and integration name shown to users.
- `ocpp` remains the protocol name and the name of the external Python package
  supplied by Mobility House. Imports such as `from ocpp.v16 import call` are
  therefore correct and do not create a dependency on another HA integration.
- OCPP wire subprotocols remain `ocpp1.6`, `ocpp2.0.1`, and `ocpp2.1`.
- The panel URL is `/ha-ocpp`; its static files are served below
  `/ha_ocpp_static`.

Versions through `0.11.x` used the Home Assistant domain `ocpp`. The new domain
is deliberately independent and is not an in-place rename of those config
entries or entities.

## Runtime Topology

```text
Charging station --OCPP WebSocket--> CentralSystem (api.py)
                                         |
                       +-----------------+-----------------+
                       |                                   |
                OCPP 1.6 handler                    OCPP 2.x handler
                       |                                   |
                       +-----------+  +--------------------+
                                   v  v
                         Shared ChargePoint metrics
                                   |
                         Home Assistant entities

Boot identity --> Wallbox profile registry --> shared normalization
Protocol handlers <--> AuthorizationManager <--> private HA Store
Admin HA OCPP panel <--> admin WebSocket API <--> backend and entities
```

One HA config entry owns one `CentralSystem` listener, its configured charging
stations, and one authorization registry. A listener accepts WebSocket paths in
the form `/<charge-point-identity>`. A previously unknown identity starts a
Home Assistant integration-discovery flow; it is not silently added as a fully
configured station.

The config model and management panel can enumerate several entries on
different ports, and panel commands carry an explicit `entry_id`. Multi-server
operation is not yet a complete public contract, however: `ha_ocpp.*` services
are domain-global but are currently registered by each `CentralSystem`, and
unloading one entry removes those services. Until service ownership is moved to
a domain-level router, one loaded central-system entry is the supported
operational topology.

The config entry stores server and station settings. Live OCPP metrics are kept
in memory and exposed through entities. RFID users and credentials are stored
separately with Home Assistant's private `Store`, using a key below the
`ha_ocpp` domain.

## Layer Responsibilities

### Transport and lifecycle

`__init__.py`, `config_flow.py`, and `api.py` own Home Assistant setup, config
entries, the WebSocket listener, OCPP subprotocol negotiation, connection
routing, and service registration.

### Protocol adapters

`ocppv16.py` and `ocppv201.py` translate version-specific messages to the
shared model. The 2.x adapter handles the currently supported OCPP 2.0.1 and
experimental 2.1 paths. Version-specific payload details must remain here.

### Shared station model

`chargepoint.py` owns common metrics, connector-aware routing, phase
aggregation, connection monitoring, and behavior shared across protocol
versions. Generic standards-compliant stations must work without a product
profile.

### Wallbox profiles

`wallbox_profiles/` contains declarative identity matching, presentation
metadata, capability notes, and narrowly scoped normalization. A profile is not
a second OCPP client and must not duplicate protocol handlers or entity
platforms. See [Wallbox Profiles](wallbox-profiles.md).

In the current implementation, `charging_limit_strategy` and capability hints
are descriptive metadata exposed to the panel; only value normalization is
dispatched through the profile object. The hardware-verified Autel charging
limit uses the generic OCPP 1.6 maximum-rate implementation rather than a
vendor-specific message handler.

### Home Assistant interfaces

`sensor.py`, `switch.py`, `number.py`, and `button.py` expose stable entities
for dashboards and automations. Connector-specific entities belong to child
connector devices; station-wide entities belong to the charging-station device.

`dashboard.py` registers the sidebar panel and an administrator-only Home
Assistant WebSocket API. The panel operates through the same central-system,
entity, config-entry, and authorization objects as the standard HA interfaces;
it is not a second backend.

## Charging Limits

For OCPP 1.6, HA OCPP reads
`ChargingScheduleAllowedChargingRateUnit` after connection and stores the
normalized advertised units in the station settings. It exposes station-wide
`Maximum Current` for `Current`, `Maximum Power` for `Power`, or both when both
are advertised.

Station-wide limits use `ChargePointMaxProfile` on connector `0`. The generic
OCPP 1.6 path uses an absolute profile for the dedicated maximum-rate entities.
The Autel MaxiCharger power path is physically verified with the same shape.
Multi-connector stations retain separate current controls for each connector;
those controls do not replace the station-wide ceiling.

The configured maximum current and power are administrator safety bounds for
the HA controls. OCPP 1.6 advertises allowed units but does not provide a
portable nameplate-capacity value, so accepting a charging profile is not proof
that the requested value is within the station's electrical rating.

## Authorization and Privacy

`AuthorizationManager` evaluates OCPP authorization for each central system.
Unknown credentials are accepted by default for backwards compatibility; the
administrator can enable registered-only mode. An enrollment scan is always
rejected for charging and then captured for assignment.

The management WebSocket commands require a Home Assistant administrator. The
admin panel can display complete RFID values so credentials can be managed.
Regular user-status entities expose only masked identifiers. Complete values
remain in private HA storage and must not be logged or placed in normal entity
attributes.

RFID authorization controls whether a transaction is accepted. It does not
authenticate the charger's WebSocket connection. Optional TLS protects the
transport, but HA OCPP does not currently validate client certificates or a
station credential during the WebSocket handshake.

## Change Rules

- Keep standards-compliant behavior in the generic protocol layers.
- Add a wallbox profile only for observed product metadata or a bounded,
  tested difference.
- Do not let product images or labels alter protocol behavior.
- Keep public Home Assistant names under `ha_ocpp`; retain `ocpp` only where it
  means the protocol or Python dependency.
- Add tests at the owning layer: protocol tests for wire behavior, profile tests
  for matching and normalization, entity tests for HA contracts, and dashboard
  tests for management commands.

`GetCompositeSchedule` is not part of the current implementation and is outside
this architecture revision.
