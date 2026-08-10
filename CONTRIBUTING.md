# Contributing to HA OCPP

Bug fixes, charger reports, documentation, tests, and focused features are
welcome. Use [GitHub issues](https://github.com/alex89rm/ha-ocpp/issues) for
reproducible bugs and pull requests for reviewed changes.

## Development Flow

1. Fork the repository and create a focused branch from `main`.
2. Keep standards-compliant behavior in the generic protocol layers.
3. Put product-specific metadata and bounded quirks in a wallbox profile; do
   not fork the OCPP client or entity platforms for one vendor.
4. Add tests at the layer that owns the behavior.
5. Update documentation and translations for user-visible changes.
6. Run the repository checks before opening a pull request.

Read [Architecture](docs/architecture.md) and
[Wallbox Profiles](docs/wallbox-profiles.md) before changing protocol routing or
adding a product module.

## Environment

Create a virtual environment and install the repository requirements. On Linux
or macOS:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

On PowerShell, activate with `venv\Scripts\Activate.ps1`.

## Tests and Formatting

Run the complete test suite:

```bash
pytest
```

The project coverage settings are in `setup.cfg` and require at least 95%
coverage. Run all configured formatting and repository checks with:

```bash
pre-commit run --all-files
```

The Python formatter and linter are Ruff. Do not describe Black or Prettier as
the required project workflow unless the pre-commit configuration changes.

Build the Sphinx documentation with warnings treated as errors:

```bash
python -m sphinx -W --keep-going -b html docs docs/_build/html
```

## Bug Reports

Include:

- HA OCPP and Home Assistant versions;
- station vendor, exact model, firmware, OCPP version, and connector count;
- selected wallbox profile;
- steps to reproduce, expected behavior, and actual behavior;
- a short redacted debug log around the failure.

Never publish complete RFID tokens, certificates, passwords, or private network
details. Use a private
[security advisory](https://github.com/alex89rm/ha-ocpp/security/advisories/new)
for vulnerabilities.

## License

Contributions are licensed under the repository's [MIT License](LICENSE).
