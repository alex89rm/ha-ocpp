# Development

Start with the repository
[contribution guide](https://github.com/alex89rm/ha-ocpp/blob/main/CONTRIBUTING.md),
[architecture](architecture.md), and [wallbox profile rules](wallbox-profiles.md).

The runtime integration lives in `custom_components/ha_ocpp`. Public Home
Assistant identifiers use the `ha_ocpp` domain. The external `ocpp` Python
package and wire subprotocol names keep their protocol-defined names.

Run these checks from the repository root:

```bash
pytest
pre-commit run --all-files
python -m sphinx -W --keep-going -b html docs docs/_build/html
```

The included devcontainer can run a standalone Home Assistant instance with the
integration mounted from the workspace. GitHub Codespaces can use the same
configuration.

Protocol changes require version-specific tests. Shared metric changes require
connector-aware tests. Product profiles require matching and fallback tests.
Panel commands require administrator WebSocket API tests as well as tests for
the underlying entity or manager operation.
