"""Support for MelCloud device sensors."""

from __future__ import annotations

from pymelcloud import DEVICE_TYPE_ERV, ErvDevice

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import StateType

from . import MelCloudDevice
from .const import DOMAIN, MEL_DEVICES


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up MelCloud device climate based on config_entry."""
    mel_devices = hass.data[DOMAIN][entry.entry_id].get(MEL_DEVICES)
    entities = []
    entities.extend(
        [
            ErvVentilationModeSelect(mel_device, mel_device.device)
            for mel_device in mel_devices[DEVICE_TYPE_ERV]
        ]
    )
    async_add_entities(entities, True)


class ErvVentilationModeSelect(SelectEntity):
    """ERV fan device."""

    def __init__(self, device: MelCloudDevice, erv_device: ErvDevice) -> None:
        """Initialize the fan."""
        self.api = device
        self._base_device = self.api.device
        self._device = erv_device
        self._attr_name = f"{self._device.name} Ventilation Mode"
        self._attr_unique_id = f"{erv_device.serial}-{erv_device.mac}_ventilation_mode"

    @property
    def state(self) -> StateType:
        """Return the state of the entity."""
        return self._device.ventilation_mode

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return self._device.ventilation_modes

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        set_dict = {"ventilation_mode": option}
        await self._device.set(set_dict)
