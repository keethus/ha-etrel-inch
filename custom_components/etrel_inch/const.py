"""Constants for the Etrel INCH integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "etrel_inch"

# Configuration keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_SLAVE_ID: Final = "slave_id"
CONF_NAME: Final = "name"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_ENABLE_WRITES: Final = "enable_writes"

# Defaults
DEFAULT_PORT: Final = 502
DEFAULT_SLAVE_ID: Final = 1
DEFAULT_POLL_INTERVAL: Final = 10
DEFAULT_NAME: Final = "Etrel INCH"
MIN_POLL_INTERVAL: Final = 2
MAX_POLL_INTERVAL: Final = 60

MANUFACTURER: Final = "Etrel"

# Verified register map (firmware OS 5.0 / SW 5.4)
# All addresses are 0-based holding-register offsets.
REG_CHARGE_STATUS: Final = 0          # int16,  R
REG_NUM_PHASES: Final = 1             # int16,  R (1 or 3)
REG_DEPARTURE_TIME_SET: Final = 4     # int64,  W (4 regs, unix)
REG_ACTIVE_POWER: Final = 26          # float32 R (kW)
REG_SESSION_ENERGY: Final = 30        # float32 R (kWh)
REG_SESSION_DURATION: Final = 32      # int64,  R (seconds)
REG_DEPARTURE_TIME_READ: Final = 36   # int64,  R (unix)
REG_SERIAL_NUMBER: Final = 990        # string[10]
REG_MODEL: Final = 1000               # string[10]
REG_HW_VERSION: Final = 1010          # string[5]
REG_SW_VERSION: Final = 1015          # string[5]

# Charge status enum
CHARGE_STATUS_MAP: Final[dict[int, str]] = {
    1: "available",
    2: "waiting_for_vehicle",
    3: "waiting_to_start",
    4: "charging",
    5: "vehicle_paused",
    6: "charger_paused",
    7: "charge_ended",
    8: "error",
    9: "resuming",
    10: "unavailable",
}

CHARGE_STATUS_OPTIONS: Final = list(CHARGE_STATUS_MAP.values()) + ["unknown"]

# TODO: Verify these placeholder write registers on Etrel INCH firmware 5.4
# Suggested verification: read the Etrel Modbus documentation for your exact
# model, or probe with `mbpoll -m tcp -a <slave_id> -r <addr> -t 4 <host>`.
# The number/switch entities are gated behind CONF_ENABLE_WRITES until the
# correct addresses are confirmed.
REG_CHARGING_CURRENT_SETPOINT_PLACEHOLDER: Final = 1000  # PLACEHOLDER
REG_CHARGING_PAUSE_PLACEHOLDER: Final = 1001             # PLACEHOLDER

CURRENT_SETPOINT_MIN_A: Final = 6
CURRENT_SETPOINT_MAX_A: Final = 32
