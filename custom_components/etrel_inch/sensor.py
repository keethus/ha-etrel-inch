"""Sensor platform for the Etrel INCH charger."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo as HaDeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CHARGE_STATUS_MAP, CHARGE_STATUS_OPTIONS, DOMAIN, MANUFACTURER
from .coordinator import EtrelCoordinator


@dataclass(frozen=True, kw_only=True)
class EtrelSensorDescription(SensorEntityDescription):
    """Describe how to derive a sensor value from coordinator data + device info."""

    value_fn: Callable[[dict[str, Any], EtrelCoordinator], Any]


def _status_text(data: dict[str, Any], _: EtrelCoordinator) -> str:
    raw = data.get("charge_status")
    if isinstance(raw, int) and raw in CHARGE_STATUS_MAP:
        return CHARGE_STATUS_MAP[raw]
    return "unknown"


SENSORS: tuple[EtrelSensorDescription, ...] = (
    EtrelSensorDescription(
        key="charge_status",
        translation_key="charge_status",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGE_STATUS_OPTIONS,
        value_fn=_status_text,
    ),
    EtrelSensorDescription(
        key="active_power",
        translation_key="active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=lambda d, _c: round(float(d["active_power_kw"]), 3),
    ),
    EtrelSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda d, _c: round(float(d["session_energy_kwh"]), 3),
    ),
    EtrelSensorDescription(
        key="session_duration",
        translation_key="session_duration",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda d, _c: int(d["session_duration_s"]),
    ),
    EtrelSensorDescription(
        key="num_phases",
        translation_key="num_phases",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d, _c: int(d["num_phases"]),
    ),
    EtrelSensorDescription(
        key="model",
        translation_key="model",
        entity_registry_enabled_default=False,
        value_fn=lambda _d, c: c.device_info.model,
    ),
    EtrelSensorDescription(
        key="sw_version",
        translation_key="sw_version",
        entity_registry_enabled_default=False,
        value_fn=lambda _d, c: c.device_info.sw_version,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtrelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(EtrelSensor(coordinator, desc) for desc in SENSORS)


class EtrelSensor(CoordinatorEntity[EtrelCoordinator], SensorEntity):
    """A single sensor on the charger."""

    entity_description: EtrelSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EtrelCoordinator,
        description: EtrelSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.device_info.serial_number
        self._attr_unique_id = f"{serial}_{description.key}"
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
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        try:
            return self.entity_description.value_fn(self.coordinator.data, self.coordinator)
        except (KeyError, TypeError, ValueError):
            return None
