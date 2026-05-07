"""Button platform — one-shot command writes.

- stop_charging:           addr 1
- release_current_setpoint: addr 10  (cancel current override)
- release_power_setpoint:   addr 13  (cancel power override)
- restart_charger:          addr 1004 (soft reboot)

All gated behind CONF_ENABLE_WRITES.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENABLE_WRITES,
    DOMAIN,
    REG_W_CANCEL_CURRENT,
    REG_W_CANCEL_POWER,
    REG_W_RESTART,
    REG_W_STOP_CHARGING,
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
    async_add_entities(
        [
            EtrelOneShotButton(
                coordinator,
                key="stop_charging",
                address=REG_W_STOP_CHARGING,
            ),
            EtrelOneShotButton(
                coordinator,
                key="release_current_setpoint",
                address=REG_W_CANCEL_CURRENT,
                entity_registry_enabled_default=False,
            ),
            EtrelOneShotButton(
                coordinator,
                key="release_power_setpoint",
                address=REG_W_CANCEL_POWER,
                entity_registry_enabled_default=False,
            ),
            EtrelOneShotButton(
                coordinator,
                key="restart_charger",
                address=REG_W_RESTART,
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=False,
            ),
        ]
    )


class EtrelOneShotButton(CoordinatorEntity[EtrelCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EtrelCoordinator,
        *,
        key: str,
        address: int,
        entity_category: EntityCategory | None = None,
        entity_registry_enabled_default: bool = True,
    ) -> None:
        super().__init__(coordinator)
        self._address = address
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.device_info.serial_number}_{key}"
        self._attr_device_info = build_device_info(coordinator)
        if entity_category is not None:
            self._attr_entity_category = entity_category
        self._attr_entity_registry_enabled_default = entity_registry_enabled_default

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.write_bool(address=self._address)
        except EtrelModbusError as err:
            _LOGGER.error(
                "Button %s (addr %s) failed: %s",
                self._attr_translation_key,
                self._address,
                err,
            )
            raise
        await self.coordinator.async_request_refresh()
