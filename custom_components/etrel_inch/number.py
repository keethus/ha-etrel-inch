"""Number platform — charging current setpoint (PLACEHOLDER, write-gated)."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo as HaDeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENABLE_WRITES,
    CURRENT_SETPOINT_MAX_A,
    CURRENT_SETPOINT_MIN_A,
    DOMAIN,
    MANUFACTURER,
    REG_CHARGING_CURRENT_SETPOINT_PLACEHOLDER,
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
        # Writes disabled — do not register the entity at all.
        return

    coordinator: EtrelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EtrelChargingCurrentNumber(coordinator)])


class EtrelChargingCurrentNumber(CoordinatorEntity[EtrelCoordinator], NumberEntity):
    """Set the charging current limit (amps).

    NOTE: register address is a PLACEHOLDER. Verify against your firmware
    before relying on this entity in automations.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "charging_current_setpoint"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = float(CURRENT_SETPOINT_MIN_A)
    _attr_native_max_value = float(CURRENT_SETPOINT_MAX_A)
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: EtrelCoordinator) -> None:
        super().__init__(coordinator)
        serial = coordinator.device_info.serial_number
        self._attr_unique_id = f"{serial}_charging_current_setpoint"
        self._attr_device_info = HaDeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer=MANUFACTURER,
            name=coordinator.entry.title,
            model=coordinator.device_info.model or None,
            sw_version=coordinator.device_info.sw_version or None,
            hw_version=coordinator.device_info.hw_version or None,
            serial_number=serial or None,
        )
        self._last_value: float | None = None

    @property
    def native_value(self) -> float | None:
        return self._last_value

    async def async_set_native_value(self, value: float) -> None:
        amps = max(
            CURRENT_SETPOINT_MIN_A,
            min(CURRENT_SETPOINT_MAX_A, int(round(value))),
        )
        try:
            await self.coordinator.client.write_current_setpoint(
                address=REG_CHARGING_CURRENT_SETPOINT_PLACEHOLDER,
                amps=amps,
            )
        except EtrelModbusError as err:
            _LOGGER.error("Failed to write current setpoint: %s", err)
            raise
        self._last_value = float(amps)
        self.async_write_ha_state()
