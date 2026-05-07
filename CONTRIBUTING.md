# Contributing

Contributions are welcome — bug reports, fixes, register-map additions for
new firmwares, translations, docs improvements. The bar is "make the
integration more useful for people running Home Assistant against an Etrel
INCH charger over Modbus TCP".

## Quick start

```bash
git clone https://github.com/keethus/ha-etrel-inch.git
cd ha-etrel-inch
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest          # tests (none yet — PRs welcome)
mypy            # type check (strict)
ruff check .    # lint
ruff format .   # format
```

`mypy --strict` and `ruff check` must pass before a PR can land. Tests are
not blocking yet, but new behavior should ship with coverage.

## Pull requests

1. Fork and create a branch from `main`.
2. Keep changes focused — one logical change per PR.
3. Add or update tests for behavior changes. The integration ships with
   `mypy --strict`, so type annotations are required.
4. Update [README.md](README.md) if user-visible behavior changed.
5. Open the PR; CI runs hassfest, the HACS Action, and the linters.

## Verifying register addresses

The placeholder write registers (`REG_CHARGING_CURRENT_SETPOINT_PLACEHOLDER`,
`REG_CHARGING_PAUSE_PLACEHOLDER`) in
[`const.py`](custom_components/etrel_inch/const.py) are firmware-dependent
and **unverified** for OS 5.0 / SW 5.4. If you confirm the right addresses
on your firmware:

1. Probe with `mbpoll -m tcp -a <slave_id> -r <addr> -t 4 -c 1 <host>` and
   note both the read-back format (uint16, float32, …) and the encoding
   semantics (e.g. amps vs deci-amps).
2. Update the constants and the encoding in
   [`modbus_client.py`](custom_components/etrel_inch/modbus_client.py).
3. Note the firmware version you tested in your PR description.
4. Add or update tests covering the encode/decode path.

## Bug reports

Use [GitHub Issues](https://github.com/keethus/ha-etrel-inch/issues).
Helpful reports include:

- Home Assistant version
- Integration version (from `manifest.json`)
- Charger **firmware versions** (OS / SW / Web — visible in the charger's
  web UI under *About*)
- A redacted snippet from **Settings → System → Logs** at DEBUG level (set
  via `logger:` config — see the README troubleshooting section).
- Steps to reproduce.

## License

By contributing you agree that your contributions will be licensed under the
[MIT License](LICENSE).
