"""Switch platform — pause/resume charging (PLACEHOLDER, write-gated)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo as HaDeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CHARGE_STATUS_MAP,
    CONF_ENABLE_WRITES,
    DOMAIN,
    MANUFACTURER,
    REG_CHARGING_PAUSE_PLACEHOLDER,
)
from .coordinator import EtrelCoordinator
from .modbus_client import EtrelModbusError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if not entry.options.get(CONF_ENABLE_WRITES, False):
        return

    coordinator: EtrelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EtrelPauseSwitch(coordinator)])


class EtrelPauseSwitch(CoordinatorEntity[EtrelCoordinator], SwitchEntity):
    """Pause/resume charging.

    NOTE: register address is a PLACEHOLDER. Verify against your firmware.
    Reflected state is derived from the charge_status enum (charger_paused).
    """

    _attr_has_entity_name = True
    _attr_translation_key = "charging_paused"

    def __init__(self, coordinator: EtrelCoordinator) -> None:
        super().__init__(coordinator)
        serial = coordinator.device_info.serial_number
        self._attr_unique_id = f"{serial}_charging_paused"
        self._attr_device_info = HaDeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer=MANUFACTURER,
            name=coordinator.entry.title,
            model=coordinator.device_info.model or None,
            sw_version=coordinator.device_info.sw_version or None,
            hw_version=coordinator.device_info.hw_version or None,
            serial_number=serial or None,
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return None
        raw = data.get("charge_status")
        if isinstance(raw, int) and raw in CHARGE_STATUS_MAP:
            return CHARGE_STATUS_MAP[raw] == "charger_paused"
        return None

    async def async_turn_on(self, **_kwargs: Any) -> None:
        try:
            await self.coordinator.client.write_pause(
                address=REG_CHARGING_PAUSE_PLACEHOLDER,
                paused=True,
            )
        except EtrelModbusError as err:
            _LOGGER.error("Failed to pause charging: %s", err)
            raise
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        try:
            await self.coordinator.client.write_pause(
                address=REG_CHARGING_PAUSE_PLACEHOLDER,
                paused=False,
            )
        except EtrelModbusError as err:
            _LOGGER.error("Failed to resume charging: %s", err)
            raise
        await self.coordinator.async_request_refresh()
