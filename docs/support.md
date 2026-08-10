# Support

Use a [GitHub discussion](https://github.com/alex89rm/ha-ocpp/discussions) for
setup questions and the [issue tracker](https://github.com/alex89rm/ha-ocpp/issues)
for reproducible bugs. Security reports belong in a private
[security advisory](https://github.com/alex89rm/ha-ocpp/security/advisories/new).

Before reporting a problem:

1. Confirm the installed HA OCPP version and Home Assistant version.
2. Record the station vendor, exact model, firmware, OCPP version, and connector
   count.
3. Reproduce with debug logging from [Debugging](debugging.md).
4. State whether the Generic profile or a product profile was selected.
5. Redact RFID values, public addresses, certificates, and other secrets.

Historical reports from the original `lbbrhzn/ocpp` project can provide useful
firmware context, but they do not prove that the current HA OCPP code has the
same behavior. Reproduce against the current HA OCPP release before opening an
issue here.

## Charging Profiles

If a station behaves unexpectedly after a maximum-rate change, inspect its
Smart Charging support and allowed charging-rate units first. To deliberately
remove profiles, call:

```yaml
action: ha_ocpp.clear_profile
data:
  devid: garage_wallbox
```

Clearing profiles can remove the station-wide safety ceiling as well as
transaction profiles. Apply the required maximum again after the test.

## Reboot Notifications

HA OCPP can create persistent notifications when a station reboots or reports a
protocol warning. Repeated reboot notifications usually indicate an unstable
network, rejected configuration exchange, or station firmware loop. Diagnose
the cause before suppressing the notification in an automation.
