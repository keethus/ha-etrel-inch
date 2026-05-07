"""The Etrel INCH EV charger integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_HOST,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_SLAVE_ID,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SLAVE_ID,
    DOMAIN,
)
from .coordinator import EtrelCoordinator
from .modbus_client import EtrelModbusClient, EtrelModbusError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Etrel INCH from a config entry."""
    host: str = entry.data[CONF_HOST]
    port: int = entry.data.get(CONF_PORT, DEFAULT_PORT)
    slave_id: int = entry.data.get(CONF_SLAVE_ID, DEFAULT_SLAVE_ID)
    poll_interval: int = entry.options.get(
        CONF_POLL_INTERVAL,
        entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
    )

    client = EtrelModbusClient(host=host, port=port, slave_id=slave_id)

    try:
        await client.connect()
        # Connectivity probe — fails fast if the charger isn't reachable.
        await client.probe_connectivity()
        # Identity is best-effort; empty fields are tolerated.
        device_info = await client.read_device_info()
    except EtrelModbusError as err:
        await client.close()
        raise ConfigEntryNotReady(f"Failed to reach Etrel INCH at {host}: {err}") from err

    # Stable serial fallback for the device-registry identifier when the
    # charger doesn't expose its serial at register 990.
    if not device_info.serial_number:
        device_info.serial_number = f"etrel_inch_{host}_{slave_id}"

    coordinator = EtrelCoordinator(
        hass=hass,
        entry=entry,
        client=client,
        poll_interval=poll_interval,
        device_info=device_info,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: EtrelCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change (e.g. poll interval, write toggle)."""
    await hass.config_entries.async_reload(entry.entry_id)
