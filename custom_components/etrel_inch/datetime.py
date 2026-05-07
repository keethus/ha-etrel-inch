"""DateTime platform — set / read the EV's planned departure time.

Writes int64 unix timestamp to holding reg 4 (4 registers).
Reads the same field from input reg 36 (also a sensor with TIMESTAMP class).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_WRITES, DOMAIN, REG_W_DEPARTURE_TIME
from .coordinator import EtrelCoordinator
from .modbus_client import EtrelModbusError
from .sensor import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if not entry.options.get(CONF_ENABLE_WRITES, False):
        return
    coordinator: EtrelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EtrelDepartureTime(coordinator)])


class EtrelDepartureTime(CoordinatorEntity[EtrelCoordinator], DateTimeEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "departure_time"

    def __init__(self, coordinator: EtrelCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_info.serial_number}_departure_time"
        self._attr_device_info = build_device_info(coordinator)

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        if not data:
            return None
        unix = data.get("session_departure_unix")
        if not isinstance(unix, int) or unix <= 0:
            return None
        try:
            return datetime.fromtimestamp(unix, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    async def async_set_value(self, value: datetime) -> None:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        unix = int(value.timestamp())
        try:
            await self.coordinator.client.write_departure_time(
                address=REG_W_DEPARTURE_TIME,
                unix=unix,
            )
        except EtrelModbusError as err:
            _LOGGER.error("Failed to write departure time: %s", err)
            raise
        await self.coordinator.async_request_refresh()
