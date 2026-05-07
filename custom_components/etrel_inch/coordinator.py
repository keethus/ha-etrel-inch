"""DataUpdateCoordinator for the Etrel INCH charger."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .modbus_client import DeviceInfo, EtrelModbusClient, EtrelModbusError

_LOGGER = logging.getLogger(__name__)


class EtrelCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Polls the charger on a fixed interval. Watchdog-aware."""

    device_info: DeviceInfo

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: EtrelModbusClient,
        poll_interval: int,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.entry = entry
        self.client = client
        self.device_info = device_info

    async def _async_update_data(self) -> dict[str, object]:
        try:
            return await self.client.read_dynamic()
        except EtrelModbusError as err:
            raise UpdateFailed(str(err)) from err

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.client.close()
