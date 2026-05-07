"""Thin async wrapper around pymodbus for the Etrel INCH charger."""
from __future__ import annotations

import asyncio
import inspect
import logging
import struct
from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0
REQUEST_TIMEOUT = 5.0

# pymodbus renamed `slave` -> `device_id` in 3.7 and removed `slave` in 3.8.
# Detect once at import time so we work on both old and new HA bundles.
_READ_PARAMS = inspect.signature(
    AsyncModbusTcpClient.read_holding_registers
).parameters
_SLAVE_KW = "device_id" if "device_id" in _READ_PARAMS else "slave"


class EtrelModbusError(Exception):
    """Raised on any Modbus-level failure talking to the charger."""


@dataclass(slots=True)
class DeviceInfo:
    """Static device-identity fields read once at setup."""

    serial_number: str
    model: str
    hw_version: str
    sw_version: str


class EtrelModbusClient:
    """Encapsulates an AsyncModbusTcpClient + decoding for one charger."""

    def __init__(self, host: str, port: int, slave_id: int) -> None:
        self._host = host
        self._port = port
        self._slave_id = slave_id
        self._client: AsyncModbusTcpClient | None = None
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    @property
    def slave_id(self) -> int:
        return self._slave_id

    async def connect(self) -> None:
        """Open the TCP connection. Idempotent."""
        if self._client is not None and self._client.connected:
            return
        self._client = AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=CONNECT_TIMEOUT,
        )
        try:
            ok = await asyncio.wait_for(self._client.connect(), timeout=CONNECT_TIMEOUT)
        except (asyncio.TimeoutError, ConnectionException) as err:
            raise EtrelModbusError(f"Connection to {self._host}:{self._port} failed") from err
        if not ok or not self._client.connected:
            raise EtrelModbusError(f"Connection to {self._host}:{self._port} refused")

    async def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - close should not propagate
                _LOGGER.debug("Error closing modbus client", exc_info=True)
            self._client = None

    async def _read(self, address: int, count: int) -> list[int]:
        """Read holding registers with a connection-restoring retry."""
        async with self._lock:
            await self.connect()
            assert self._client is not None
            try:
                rr = await asyncio.wait_for(
                    self._client.read_holding_registers(
                        address=address,
                        count=count,
                        **{_SLAVE_KW: self._slave_id},
                    ),
                    timeout=REQUEST_TIMEOUT,
                )
            except (asyncio.TimeoutError, ConnectionException, ModbusException) as err:
                await self.close()
                raise EtrelModbusError(
                    f"Read failed at {address}+{count}: {err}"
                ) from err
            if rr.isError():
                raise EtrelModbusError(f"Modbus error at {address}+{count}: {rr}")
            return list(rr.registers)

    async def _write_registers(self, address: int, values: list[int]) -> None:
        async with self._lock:
            await self.connect()
            assert self._client is not None
            try:
                rr = await asyncio.wait_for(
                    self._client.write_registers(
                        address=address,
                        values=values,
                        **{_SLAVE_KW: self._slave_id},
                    ),
                    timeout=REQUEST_TIMEOUT,
                )
            except (asyncio.TimeoutError, ConnectionException, ModbusException) as err:
                await self.close()
                raise EtrelModbusError(
                    f"Write failed at {address}: {err}"
                ) from err
            if rr.isError():
                raise EtrelModbusError(f"Modbus write error at {address}: {rr}")

    # ----- decoders (big-endian word, big-endian byte — Etrel default) -----

    @staticmethod
    def _decode_int16(regs: list[int], offset: int = 0) -> int:
        raw = struct.pack(">H", regs[offset] & 0xFFFF)
        return struct.unpack(">h", raw)[0]

    @staticmethod
    def _decode_uint16(regs: list[int], offset: int = 0) -> int:
        return regs[offset] & 0xFFFF

    @staticmethod
    def _decode_int64(regs: list[int], offset: int = 0) -> int:
        raw = struct.pack(">HHHH", *(r & 0xFFFF for r in regs[offset:offset + 4]))
        return struct.unpack(">q", raw)[0]

    @staticmethod
    def _decode_float32(regs: list[int], offset: int = 0) -> float:
        raw = struct.pack(">HH", regs[offset] & 0xFFFF, regs[offset + 1] & 0xFFFF)
        return struct.unpack(">f", raw)[0]

    @staticmethod
    def _decode_string(regs: list[int]) -> str:
        raw = b"".join(struct.pack(">H", r & 0xFFFF) for r in regs)
        return raw.decode("ascii", errors="replace").replace("\x00", "").strip()

    @staticmethod
    def _encode_int64(value: int) -> list[int]:
        raw = struct.pack(">q", value)
        return list(struct.unpack(">HHHH", raw))

    # ----- high-level reads -----

    async def read_dynamic(self) -> dict[str, object]:
        """Read all polled runtime data in two contiguous blocks."""
        # Block A: regs 0-1 (status + phases)
        block_a = await self._read(address=0, count=2)
        # Block B: regs 26-39 (power, energy, duration, departure_read)
        block_b = await self._read(address=26, count=14)

        return {
            "charge_status": self._decode_int16(block_a, 0),
            "num_phases": self._decode_int16(block_a, 1),
            "active_power_kw": self._decode_float32(block_b, 0),       # 26-27
            "session_energy_kwh": self._decode_float32(block_b, 4),    # 30-31
            "session_duration_s": self._decode_int64(block_b, 6),      # 32-35
            "departure_time_unix": self._decode_int64(block_b, 10),    # 36-39
        }

    async def read_device_info(self) -> DeviceInfo:
        """Read static identity registers (990-1019). Tolerant of zeros/missing
        firmware identity blocks — returns empty strings on miss, callers must
        substitute defaults."""
        try:
            block = await self._read(address=990, count=30)
        except EtrelModbusError as err:
            _LOGGER.debug("Identity read at 990 failed: %s — using empty defaults", err)
            return DeviceInfo(serial_number="", model="", hw_version="", sw_version="")

        info = DeviceInfo(
            serial_number=self._decode_string(block[0:10]),
            model=self._decode_string(block[10:20]),
            hw_version=self._decode_string(block[20:25]),
            sw_version=self._decode_string(block[25:30]),
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Identity registers 990-1019 raw=%s decoded=%s",
                block, info,
            )
        return info

    async def probe_connectivity(self) -> dict[str, int]:
        """Validate connectivity by reading the dynamic block at regs 0-1.
        These are populated on every Etrel INCH regardless of commissioning."""
        block = await self._read(address=0, count=2)
        return {
            "charge_status": self._decode_int16(block, 0),
            "num_phases": self._decode_int16(block, 1),
        }

    # ----- writes (PLACEHOLDER — gated by CONF_ENABLE_WRITES) -----

    async def write_current_setpoint(self, address: int, amps: int) -> None:
        # TODO: confirm encoding (single uint16 vs float32) and address.
        await self._write_registers(address=address, values=[amps & 0xFFFF])

    async def write_pause(self, address: int, paused: bool) -> None:
        # TODO: confirm encoding and address (likely 0=resume / 1=pause).
        await self._write_registers(address=address, values=[1 if paused else 0])
