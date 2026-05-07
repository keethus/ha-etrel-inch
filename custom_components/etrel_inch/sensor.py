"""Sensor platform for the Etrel INCH charger.

Every register exposed by the charger is a sensor here. Diagnostic / static
identity sensors are disabled by default; users enable the ones they want.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo as HaDeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CHARGE_STATUS_MAP,
    CHARGE_STATUS_OPTIONS,
    CONNECTOR_TYPE_MAP,
    CONNECTOR_TYPE_OPTIONS,
    DOMAIN,
    MANUFACTURER,
    PHASE_MODE_MAP,
    PHASE_MODE_OPTIONS,
)
from .coordinator import EtrelCoordinator


@dataclass(frozen=True, kw_only=True)
class EtrelSensorDescription(SensorEntityDescription):
    """Describe how to derive a sensor value from coordinator data + device info."""

    value_fn: Callable[[dict[str, Any], EtrelCoordinator], Any]


# ----- value_fn helpers -----

def _enum_lookup(field: str, mapping: dict[int, str]) -> Callable[..., Any]:
    def _fn(data: dict[str, Any], _: EtrelCoordinator) -> str:
        raw = data.get(field)
        if isinstance(raw, int) and raw in mapping:
            return mapping[raw]
        return "unknown"
    return _fn


def _float_field(field: str, precision: int | None = None) -> Callable[..., Any]:
    def _fn(data: dict[str, Any], _: EtrelCoordinator) -> float | None:
        v = data.get(field)
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if math.isnan(f) or math.isinf(f):
            return None
        if precision is not None:
            f = round(f, precision)
        return f
    return _fn


def _int_field(field: str) -> Callable[..., Any]:
    def _fn(data: dict[str, Any], _: EtrelCoordinator) -> int | None:
        v = data.get(field)
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    return _fn


def _timestamp_field(field: str) -> Callable[..., Any]:
    def _fn(data: dict[str, Any], _: EtrelCoordinator) -> datetime | None:
        v = data.get(field)
        if not v:
            return None
        try:
            unix = int(v)
        except (TypeError, ValueError):
            return None
        if unix <= 0:
            return None
        try:
            return datetime.fromtimestamp(unix, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return _fn


def _device_attr(attr: str) -> Callable[..., Any]:
    def _fn(_d: dict[str, Any], c: EtrelCoordinator) -> Any:
        return getattr(c.device_info, attr, None) or None
    return _fn


# ----- entity descriptions -----

SENSORS: tuple[EtrelSensorDescription, ...] = (
    # ----- status enums -----
    EtrelSensorDescription(
        key="charge_status",
        translation_key="charge_status",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGE_STATUS_OPTIONS,
        value_fn=_enum_lookup("charge_status", CHARGE_STATUS_MAP),
    ),
    EtrelSensorDescription(
        key="phase_mode",
        translation_key="phase_mode",
        device_class=SensorDeviceClass.ENUM,
        options=PHASE_MODE_OPTIONS,
        value_fn=_enum_lookup("phase_mode", PHASE_MODE_MAP),
    ),
    # ----- per-phase voltage -----
    EtrelSensorDescription(
        key="voltage_l1",
        translation_key="voltage_l1",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=_float_field("voltage_l1_v", 2),
    ),
    EtrelSensorDescription(
        key="voltage_l2",
        translation_key="voltage_l2",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=_float_field("voltage_l2_v", 2),
    ),
    EtrelSensorDescription(
        key="voltage_l3",
        translation_key="voltage_l3",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=_float_field("voltage_l3_v", 2),
    ),
    # ----- per-phase current -----
    EtrelSensorDescription(
        key="current_l1",
        translation_key="current_l1",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=_float_field("current_l1_a", 3),
    ),
    EtrelSensorDescription(
        key="current_l2",
        translation_key="current_l2",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=_float_field("current_l2_a", 3),
    ),
    EtrelSensorDescription(
        key="current_l3",
        translation_key="current_l3",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=_float_field("current_l3_a", 3),
    ),
    # ----- per-phase power -----
    EtrelSensorDescription(
        key="power_l1",
        translation_key="power_l1",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=_float_field("power_l1_kw", 3),
    ),
    EtrelSensorDescription(
        key="power_l2",
        translation_key="power_l2",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=_float_field("power_l2_kw", 3),
    ),
    EtrelSensorDescription(
        key="power_l3",
        translation_key="power_l3",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=_float_field("power_l3_kw", 3),
    ),
    # ----- aggregates -----
    EtrelSensorDescription(
        key="active_power",
        translation_key="active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=_float_field("active_power_kw", 3),
    ),
    EtrelSensorDescription(
        key="frequency",
        translation_key="frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=2,
        value_fn=_float_field("frequency_hz", 2),
    ),
    EtrelSensorDescription(
        key="power_factor",
        translation_key="power_factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        # Etrel reports a 0..1 ratio. HA's POWER_FACTOR with PERCENTAGE wants 0..100.
        value_fn=lambda d, _c: (
            None if d.get("power_factor") is None
            else round(float(d["power_factor"]) * 100.0, 2)
        ),
    ),
    # ----- current limits / setpoint readback -----
    EtrelSensorDescription(
        key="vehicle_max_current",
        translation_key="vehicle_max_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=_float_field("vehicle_max_current_a", 2),
    ),
    EtrelSensorDescription(
        key="target_current",
        translation_key="target_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=_float_field("target_current_a", 2),
    ),
    # ----- session -----
    EtrelSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=_float_field("session_energy_kwh", 4),
    ),
    EtrelSensorDescription(
        key="session_duration",
        translation_key="session_duration",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=_int_field("session_duration_s"),
    ),
    EtrelSensorDescription(
        key="session_departure_time",
        translation_key="session_departure_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_timestamp_field("session_departure_unix"),
    ),
    EtrelSensorDescription(
        key="session_id",
        translation_key="session_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_int_field("session_id"),
    ),
    # ----- EV-reported -----
    EtrelSensorDescription(
        key="ev_max_power",
        translation_key="ev_max_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=_float_field("ev_max_power_kw", 3),
    ),
    EtrelSensorDescription(
        key="ev_planned_energy",
        translation_key="ev_planned_energy",
        device_class=SensorDeviceClass.ENERGY,
        # NOT TOTAL_INCREASING — this is a target the EV reports, not a counter.
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_float_field("ev_planned_energy_kwh", 3),
    ),
    # ----- diagnostics (disabled by default) -----
    EtrelSensorDescription(
        key="custom_max_current",
        translation_key="custom_max_current",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=lambda _d, c: round(c.device_info.custom_max_current_a, 2)
        if c.device_info.custom_max_current_a
        else None,
    ),
    EtrelSensorDescription(
        key="connector_type",
        translation_key="connector_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.ENUM,
        options=CONNECTOR_TYPE_OPTIONS,
        value_fn=lambda _d, c: CONNECTOR_TYPE_MAP.get(
            c.device_info.connector_type_raw, "unknown"
        ),
    ),
    EtrelSensorDescription(
        key="num_connectors",
        translation_key="num_connectors",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda _d, c: c.device_info.num_connectors or None,
    ),
    EtrelSensorDescription(
        key="num_phases_hw",
        translation_key="num_phases_hw",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda _d, c: c.device_info.num_phases_hw or None,
    ),
    EtrelSensorDescription(
        key="phase_rotation_l1",
        translation_key="phase_rotation_l1",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda _d, c: c.device_info.l1_to_phase or None,
    ),
    EtrelSensorDescription(
        key="phase_rotation_l2",
        translation_key="phase_rotation_l2",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda _d, c: c.device_info.l2_to_phase or None,
    ),
    EtrelSensorDescription(
        key="phase_rotation_l3",
        translation_key="phase_rotation_l3",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda _d, c: c.device_info.l3_to_phase or None,
    ),
    EtrelSensorDescription(
        key="model",
        translation_key="model",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_device_attr("model"),
    ),
    EtrelSensorDescription(
        key="serial_number",
        translation_key="serial_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_device_attr("serial_number"),
    ),
    EtrelSensorDescription(
        key="sw_version",
        translation_key="sw_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_device_attr("sw_version"),
    ),
    EtrelSensorDescription(
        key="hw_version",
        translation_key="hw_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_device_attr("hw_version"),
    ),
)


def build_device_info(coordinator: EtrelCoordinator) -> HaDeviceInfo:
    """Shared device-info builder used by every platform in this integration."""
    di = coordinator.device_info
    serial = di.serial_number
    return HaDeviceInfo(
        identifiers={(DOMAIN, serial)},
        manufacturer=MANUFACTURER,
        name=coordinator.entry.title,
        model=di.model or None,
        sw_version=di.sw_version or None,
        hw_version=di.hw_version or None,
        serial_number=serial or None,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtrelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(EtrelSensor(coordinator, desc) for desc in SENSORS)


class EtrelSensor(CoordinatorEntity[EtrelCoordinator], SensorEntity):
    entity_description: EtrelSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EtrelCoordinator,
        description: EtrelSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.device_info.serial_number}_{description.key}"
        )
        self._attr_device_info = build_device_info(coordinator)

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        try:
            return self.entity_description.value_fn(self.coordinator.data, self.coordinator)
        except (KeyError, TypeError, ValueError):
            return None
