"""Switch platform — pause/resume charging.

Pause writes 1 to holding reg 2; resume writes 0 to the same register. The
displayed state is derived from the charge_status enum; when the charger
reports `charger_paused` we consider it on.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CHARGE_STATUS_MAP,
    CONF_ENABLE_WRITES,
    DOMAIN,
    REG_W_PAUSE_CHARGING,
)
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
    async_add_entities([EtrelPauseSwitch(coordinator)])


class EtrelPauseSwitch(CoordinatorEntity[EtrelCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "charging_paused"

    def __init__(self, coordinator: EtrelCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_info.serial_number}_charging_paused"
        self._attr_device_info = build_device_info(coordinator)

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
                address=REG_W_PAUSE_CHARGING,
                paused=True,
            )
        except EtrelModbusError as err:
            _LOGGER.error("Failed to pause charging: %s", err)
            raise
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        try:
            await self.coordinator.client.write_pause(
                address=REG_W_PAUSE_CHARGING,
                paused=False,
            )
        except EtrelModbusError as err:
            _LOGGER.error("Failed to resume charging: %s", err)
            raise
        await self.coordinator.async_request_refresh()
