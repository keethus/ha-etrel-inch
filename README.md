# Etrel INCH — Home Assistant integration

[![GitHub Release][release-shield]][release]
[![License][license-shield]](LICENSE)
[![hacs][hacs-shield]][hacs]

_Custom Home Assistant integration for the **Etrel INCH** family of EV
chargers. Local-polling Modbus TCP — no cloud, no extra hardware. Verified
on **INCH Pro G-PC1V5BY40** (22 kW, 3-phase, MID meter) running firmware
**OS 5.0 / SW 5.4 / Web 2.8.4**._

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Options](#options)
- [Watchdog behavior](#watchdog-behavior)
- [Writes — disabled by default](#writes--disabled-by-default)
- [Multi-charger setup](#multi-charger-setup)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Local Modbus TCP** — talks straight to the charger's port `502`. No
  Etrel cloud account, no OCPP central system, no internet required.
- **One device per charger.** Add the integration multiple times to
  monitor multiple chargers on the same LAN.
- **Watchdog-aware polling** — defaults to 10 s, configurable 2–60 s.
- **All the metrics the Energy Dashboard needs**: charge status (decoded
  to a string), active power (kW), session energy (kWh,
  `total_increasing`), session duration, active phases.
- **No third-party Python dependencies**: the integration ships with
  `requirements: []` and uses only `pymodbus` from HA core.
- **Optional, gated write controls** for charging current setpoint and
  pause/resume — disabled by default while their register addresses are
  unverified for firmware 5.4. See [Writes](#writes--disabled-by-default).

## How it works

The Etrel INCH exposes its full state over Modbus holding registers on
port `502`. The integration:

1. Opens one TCP connection per charger and reads two contiguous register
   blocks each poll cycle:
   - regs `0–1` — `charge_status`, `num_phases`
   - regs `26–39` — `active_power` (float32), `session_energy` (float32),
     `session_duration` (int64), `departure_time_read` (int64)
2. Reads regs `990–1019` once at setup for serial number, model, hardware
   and software version. The serial is used as the HA `unique_id`, which
   makes the integration safe to add multiple times for multiple chargers.
3. Decodes everything as **big-endian** for both bytes and words — the
   default Etrel convention. If your charger ships a different byte order,
   tweak the helpers in
   [`modbus_client.py`](custom_components/etrel_inch/modbus_client.py).
4. Surfaces the result through a standard
   `DataUpdateCoordinator`. Connection drops mark entities *unavailable*
   and HA applies its own exponential backoff.

## Installation

### Option 1: HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=keethus&repository=ha-etrel-inch&category=integration)

Or manually in HACS:

1. **HACS → Integrations → ⋮ (top-right) → Custom repositories**
2. Add `https://github.com/keethus/ha-etrel-inch` with category
   **Integration**.
3. Install **Etrel INCH EV Charger** and restart Home Assistant.

### Option 2: Manual

1. Download the latest release from the
   [Releases page](https://github.com/keethus/ha-etrel-inch/releases).
2. Copy `custom_components/etrel_inch/` into your HA config's
   `custom_components/` directory.
3. Restart Home Assistant.

## Configuration

Modbus must be **enabled** on the charger first — log in to the charger's
web UI, *Settings → Modbus*, switch it on. Note the slave/unit ID (default
`1`) and the `monitoring_interval` value; you'll want the HA poll interval
to be shorter than that (see [Watchdog behavior](#watchdog-behavior)).

In Home Assistant:

1. **Settings → Devices & Services → Add Integration → Etrel INCH EV Charger**.
2. Fill in:

   | Field             | Default       | Notes                                                              |
   | ----------------- | ------------- | ------------------------------------------------------------------ |
   | Name              | `Etrel INCH`  | Free-form, used as the device name in HA.                          |
   | Host / IP         | —             | Charger's LAN address. Reserve it on your DHCP server.             |
   | Modbus TCP port   | `502`         |                                                                    |
   | Slave / Unit ID   | `1`           | Whatever the charger's web UI shows.                               |
   | Poll interval (s) | `10`          | **Must** be shorter than the charger's `monitoring_interval`.      |

3. The flow validates the connection by reading the serial number (reg `990`).
   If the charger answers, the entry is created and entities show up
   within a few seconds.

## Entities

Each charger becomes one HA *device* with the following entities:

| Entity                | Class      | Source register | Notes                                          |
| --------------------- | ---------- | --------------- | ---------------------------------------------- |
| `charge_status`       | sensor     | `0` (int16)     | Decoded enum: `available`, `charging`, …       |
| `active_power`        | sensor     | `26` (float32)  | `kW`, `MEASUREMENT`, `POWER`                   |
| `session_energy`      | sensor     | `30` (float32)  | `kWh`, `TOTAL_INCREASING`, `ENERGY`            |
| `session_duration`    | sensor     | `32` (int64)    | seconds, `MEASUREMENT`, `DURATION`             |
| `num_phases`          | sensor     | `1`  (int16)    | 1 or 3                                         |
| `model`               | sensor     | `1000`          | Disabled by default; diagnostic.               |
| `sw_version`          | sensor     | `1015`          | Disabled by default; diagnostic.               |

`session_energy` is `TOTAL_INCREASING`, so it works directly as an
**Energy Dashboard** source for *Individual devices* — pick it under
*Settings → Dashboards → Energy → Add device*.

`departure_time_read` (reg `36`) is read by the coordinator but not
exposed yet. PR welcome.

## Options

Per-entry: **Settings → Devices & Services → Etrel INCH EV Charger →
Configure**:

| Option              | Default | Range          | Notes                                                                               |
| ------------------- | ------- | -------------- | ----------------------------------------------------------------------------------- |
| Poll interval       | 10 s    | 2 s – 60 s     | Live-reload — entry restarts when changed.                                          |
| Enable write controls | off   | —              | Adds the (PLACEHOLDER) current/pause entities. **Verify registers first.**          |

## Watchdog behavior

When Modbus is enabled on the charger, two parameters control the watchdog:

- `monitoring_interval` — if no Modbus read arrives within this many
  seconds, the charger drops to `fallback_current` (typically a low or
  zero amperage).
- `fallback_current` — the safe-mode amperage used after a watchdog timeout.

**Recommendations:**

- **Read-only setups** (no write controls): set `monitoring_interval = 0`
  on the charger to **disable** the watchdog entirely. The integration
  will still poll every `poll_interval` seconds, but a network blip won't
  cause the charger to throttle.
- **Setups that issue writes**: keep the watchdog enabled and ensure
  `poll_interval < monitoring_interval` with margin (e.g.
  `monitoring_interval = 30`, `poll_interval = 10`).

## Writes — disabled by default

The Etrel INCH Modbus map for write registers is firmware-dependent and not
publicly published in a single canonical document. The placeholders in
[`const.py`](custom_components/etrel_inch/const.py)
(`REG_CHARGING_CURRENT_SETPOINT_PLACEHOLDER`,
`REG_CHARGING_PAUSE_PLACEHOLDER`) are **likely wrong** for your firmware,
which is why the *Enable write controls* option is off by default.

To find the real addresses:

1. Install `mbpoll` (`brew install mbpoll` on macOS, `apt install mbpoll`
   on Debian/Ubuntu).
2. Probe documented holding registers near the typical "command" range:
   ```bash
   # read 1 register at address N (decimal), function code 3 (holding)
   mbpoll -m tcp -a 1 -r N -t 4 -c 1 192.168.x.x
   ```
3. Cross-reference with:
   - Etrel's official Modbus map for your firmware (request from your
     installer or Etrel support).
   - The Home Assistant community thread *"Etrel Inch Pro Modbus
     integration"* (forum post 736292).
   - The `evcc` Etrel driver:
     <https://github.com/evcc-io/evcc/blob/master/charger/etrel.go>.
4. Edit `REG_CHARGING_CURRENT_SETPOINT_PLACEHOLDER` and
   `REG_CHARGING_PAUSE_PLACEHOLDER` in `const.py`, restart HA, then turn
   on *Enable write controls* in the integration's options.

PRs that confirm working register addresses for a specific firmware are
very welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Multi-charger setup

Run **Add Integration → Etrel INCH EV Charger** once per charger.
Each entry is bound to its serial number (read from register `990`), so
HA refuses to add the same charger twice. Naming each entry distinctly
(`Garage`, `Driveway`, `Warehouse`) is the easiest way to keep their
entities apart in the device registry.

## Troubleshooting

**`cannot_connect` in the config flow.**
Confirm Modbus TCP is enabled on the charger, the slave ID matches, and
nothing else has the connection open — some chargers permit only one
Modbus TCP client at a time.

**Sensor values look like garbage (e.g. `active_power = 4.2e-38`).**
Almost always a byte/word ordering mismatch. The integration uses
big-endian for both bytes and words, which matches Etrel's documented
default. If your charger differs, tweak `_decode_float32` /
`_decode_int64` in
[`modbus_client.py`](custom_components/etrel_inch/modbus_client.py) and
file an issue with your firmware version.

**Charger throttles to fallback current.**
Either your poll interval is longer than `monitoring_interval`, or the
watchdog timed out during a network glitch. Disable the watchdog
(`monitoring_interval = 0`) for read-only use, or shorten the poll
interval.

**Enable debug logs** by adding to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.etrel_inch: debug
    pymodbus: info
```

## Development

```bash
git clone https://github.com/keethus/ha-etrel-inch.git
cd ha-etrel-inch
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest          # tests (none yet — PRs welcome)
mypy            # type-check (mypy --strict)
ruff check .    # lint
ruff format .   # format
```

The verified register map and the placeholder write registers live in
[`custom_components/etrel_inch/const.py`](custom_components/etrel_inch/const.py).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome — especially anything
that turns a placeholder register into a verified one.

## License

[MIT](LICENSE) © 2026 Karlis Barbars.

This project is not affiliated with Etrel d.o.o.

---

[release-shield]: https://img.shields.io/github/v/release/keethus/ha-etrel-inch?style=flat-square
[release]: https://github.com/keethus/ha-etrel-inch/releases
[license-shield]: https://img.shields.io/github/license/keethus/ha-etrel-inch?style=flat-square
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square
[hacs]: https://github.com/hacs/integration
