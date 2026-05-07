"""Async pymodbus wrapper for the Etrel INCH charger.

All runtime data is on input registers (FC 04). All writes go to holding
registers (FC 16). Big-endian byte and word order throughout. The pymodbus
keyword for slave/unit-id was renamed `slave` -> `device_id` in 3.7 and the
old name removed in 3.8 — we detect at import time and use whichever the
bundled pymodbus accepts.
"""
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
_READ_PARAMS = inspect.signature(
    AsyncModbusTcpClient.read_input_registers
).parameters
_SLAVE_KW = "device_id" if "device_id" in _READ_PARAMS else "slave"


class EtrelModbusError(Exception):
    """Raised on any Modbus-level failure talking to the charger."""


@dataclass(slots=True)
class DeviceInfo:
    """Static device-identity + hardware-config fields read once at setup."""

    serial_number: str = ""
    model: str = ""
    hw_version: str = ""
    sw_version: str = ""
    num_connectors: int = 1
    connector_type_raw: int = 0
    num_phases_hw: int = 0
    l1_to_phase: int = 0
    l2_to_phase: int = 0
    l3_to_phase: int = 0
    custom_max_current_a: float = 0.0


class EtrelModbusClient:
    """One TCP connection per charger, serialized via an async lock."""

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

    # ----- connection lifecycle -----

    async def connect(self) -> None:
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
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Error closing modbus client", exc_info=True)
            self._client = None

    # ----- low-level read/write -----

    async def _read_input(self, address: int, count: int) -> list[int]:
        """Read INPUT registers (FC 04). All Etrel runtime data lives here."""
        async with self._lock:
            await self.connect()
            assert self._client is not None
            try:
                rr = await asyncio.wait_for(
                    self._client.read_input_registers(
                        address=address,
                        count=count,
                        **{_SLAVE_KW: self._slave_id},
                    ),
                    timeout=REQUEST_TIMEOUT,
                )
            except (asyncio.TimeoutError, ConnectionException, ModbusException) as err:
                await self.close()
                raise EtrelModbusError(
                    f"Input read failed at {address}+{count}: {err}"
                ) from err
            if rr.isError():
                raise EtrelModbusError(f"Modbus error at input {address}+{count}: {rr}")
            return list(rr.registers)

    async def _write_holding(self, address: int, values: list[int]) -> None:
        """Write HOLDING registers (FC 16). All writes go here."""
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
                    f"Holding write failed at {address}: {err}"
                ) from err
            if rr.isError():
                raise EtrelModbusError(f"Modbus write error at holding {address}: {rr}")

    # ----- decoders (big-endian byte, big-endian word) -----

    @staticmethod
    def _decode_uint16(regs: list[int], offset: int = 0) -> int:
        return regs[offset] & 0xFFFF

    @staticmethod
    def _decode_int16(regs: list[int], offset: int = 0) -> int:
        raw = struct.pack(">H", regs[offset] & 0xFFFF)
        return struct.unpack(">h", raw)[0]

    @staticmethod
    def _decode_int32(regs: list[int], offset: int = 0) -> int:
        raw = struct.pack(">HH", regs[offset] & 0xFFFF, regs[offset + 1] & 0xFFFF)
        return struct.unpack(">i", raw)[0]

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

    # ----- encoders -----

    @staticmethod
    def _encode_float32(value: float) -> list[int]:
        raw = struct.pack(">f", float(value))
        return list(struct.unpack(">HH", raw))

    @staticmethod
    def _encode_int64(value: int) -> list[int]:
        raw = struct.pack(">q", int(value))
        return list(struct.unpack(">HHHH", raw))

    # ----- high-level reads -----

    async def probe_connectivity(self) -> dict[str, int]:
        """Lightweight liveness check used by the config flow. Reads regs 0-1."""
        block = await self._read_input(address=0, count=2)
        return {
            "charge_status": self._decode_uint16(block, 0),
            "phase_mode": self._decode_uint16(block, 1),
        }

    async def read_dynamic(self) -> dict[str, object]:
        """Read the full dynamic block (regs 0-47) in one request."""
        # Reg 46 is float32 → 46-47 → need count=48 from address 0.
        block = await self._read_input(address=0, count=48)

        return {
            "charge_status": self._decode_uint16(block, 0),
            "phase_mode": self._decode_uint16(block, 1),
            "vehicle_max_current_a": self._decode_float32(block, 2),
            "target_current_a": self._decode_float32(block, 4),
            "frequency_hz": self._decode_float32(block, 6),
            "voltage_l1_v": self._decode_float32(block, 8),
            "voltage_l2_v": self._decode_float32(block, 10),
            "voltage_l3_v": self._decode_float32(block, 12),
            "current_l1_a": self._decode_float32(block, 14),
            "current_l2_a": self._decode_float32(block, 16),
            "current_l3_a": self._decode_float32(block, 18),
            "power_l1_kw": self._decode_float32(block, 20),
            "power_l2_kw": self._decode_float32(block, 22),
            "power_l3_kw": self._decode_float32(block, 24),
            "active_power_kw": self._decode_float32(block, 26),
            "power_factor": self._decode_float32(block, 28),
            "session_energy_kwh": self._decode_float32(block, 30),
            "session_duration_s": self._decode_int64(block, 32),
            "session_departure_unix": self._decode_int64(block, 36),
            "session_id": self._decode_int64(block, 40),
            "ev_max_power_kw": self._decode_float32(block, 44),
            "ev_planned_energy_kwh": self._decode_float32(block, 46),
        }

    async def read_device_info(self) -> DeviceInfo:
        """Read identity + hardware-config block (regs 990-1029). Tolerant of
        zeros — returns empty/default fields if a register isn't populated."""
        try:
            block = await self._read_input(address=990, count=40)
        except EtrelModbusError as err:
            _LOGGER.debug("Identity read failed: %s — using defaults", err)
            return DeviceInfo()

        info = DeviceInfo(
            serial_number=self._decode_string(block[0:10]),
            model=self._decode_string(block[10:20]),
            hw_version=self._decode_string(block[20:25]),
            sw_version=self._decode_string(block[25:30]),
            num_connectors=self._decode_int32(block, 30),
            connector_type_raw=self._decode_uint16(block, 32),
            num_phases_hw=self._decode_uint16(block, 33),
            l1_to_phase=self._decode_uint16(block, 34),
            l2_to_phase=self._decode_uint16(block, 35),
            l3_to_phase=self._decode_uint16(block, 36),
            custom_max_current_a=self._decode_float32(block, 38),
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Device identity: %s", info)
        return info

    # ----- writes (gated by CONF_ENABLE_WRITES at the platform level) -----

    async def write_stop(self, address: int) -> None:
        await self._write_holding(address=address, values=[1])

    async def write_pause(self, address: int, paused: bool) -> None:
        await self._write_holding(address=address, values=[1 if paused else 0])

    async def write_bool(self, address: int) -> None:
        """Generic 'write 1 to fire' helper for one-shot command registers."""
        await self._write_holding(address=address, values=[1])

    async def write_current_setpoint(self, address: int, amps: float) -> None:
        await self._write_holding(address=address, values=self._encode_float32(amps))

    async def write_power_setpoint(self, address: int, kw: float) -> None:
        await self._write_holding(address=address, values=self._encode_float32(kw))

    async def write_departure_time(self, address: int, unix: int) -> None:
        await self._write_holding(address=address, values=self._encode_int64(unix))

    async def write_set_time(self, address: int, unix: int) -> None:
        await self._write_holding(address=address, values=self._encode_int64(unix))
