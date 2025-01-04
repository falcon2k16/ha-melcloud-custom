"""Platform for fan - erv integration."""

import logging
from typing import Any, Optional

from pymelcloud import DEVICE_TYPE_ERV, ErvDevice
from pymelcloud.device import PROPERTY_POWER
import pymelcloud.erv_device as erv

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from . import MelCloudDevice
from .const import (
    ATTR_ACTUAL_VENTILATION,
    ATTR_CORE_MAINTENANCE,
    ATTR_EXHAUST_VENTILATION,
    ATTR_FILTER_MAINTENANCE,
    ATTR_SUPPLY_VENTILATION,
    ATTR_VENTILATION,
    DOMAIN,
    MEL_DEVICES,
)

ORDERED_NAMED_FAN_SPEEDS = ["1", "2", "3", "4"]  # off is not included


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up MelCloud device climate based on config_entry."""
    mel_devices = hass.data[DOMAIN][entry.entry_id].get(MEL_DEVICES)
    entities = []
    entities.extend(
        [
            ErvDeviceFan(mel_device, mel_device.device)
            for mel_device in mel_devices[DEVICE_TYPE_ERV]
        ]
    )
    async_add_entities(entities, True)


class ErvDeviceFan(FanEntity):
    """ERV fan device."""

    def __init__(self, device: MelCloudDevice, erv_device: ErvDevice) -> None:
        """Initialize the fan."""
        self.api = device
        self._base_device = self.api.device
        self._device = erv_device
        self._attr_name = device.name
        self._attr_unique_id = f"{erv_device.serial}-{erv_device.mac}"
        self._attr_supported_features = (
            FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
            | FanEntityFeature.SET_SPEED
            | FanEntityFeature.PRESET_MODE
        )
        self._attr_preset_modes = ORDERED_NAMED_FAN_SPEEDS

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return self.api.device_info

    @property
    def preset_mode(self) -> str | None:
        """Set preset mode on ERV."""
        preset = self._device.fan_speed
        _LOGGER.debug("Current preset is %s", preset)
        if preset is not None:
            return preset
        return None

    @property
    def is_on(self) -> bool:
        """Return true if fan is on."""
        state = self._device.power
        _LOGGER.debug("Current state is %s", state)
        return state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the optional state attributes with device specific additions."""
        attr = {}

        ventilation_mode = self._device.ventilation_mode
        if ventilation_mode:
            attr.update({ATTR_VENTILATION: ventilation_mode})

        actual_ventilation_mode = self._device.actual_ventilation_mode
        if actual_ventilation_mode:
            attr.update({ATTR_ACTUAL_VENTILATION: actual_ventilation_mode})

        filter_maintanance_mode = self._device.filter_maintenance_required
        if filter_maintanance_mode:
            attr.update({ATTR_FILTER_MAINTENANCE: filter_maintanance_mode})

        core_maintenance_mode = self._device.core_maintenance_required
        if core_maintenance_mode:
            attr.update({ATTR_CORE_MAINTENANCE: core_maintenance_mode})

        supply_fan = self._device.actual_supply_fan_speed
        if supply_fan:
            attr.update({ATTR_SUPPLY_VENTILATION: supply_fan})

        exhaust_fan = self._device.actual_exhaust_fan_speed
        if exhaust_fan:
            attr.update({ATTR_EXHAUST_VENTILATION: exhaust_fan})
        return attr

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return len(ORDERED_NAMED_FAN_SPEEDS)

    @property
    def percentage(self) -> Optional[int]:
        """Return the current speed percentage."""
        speed = self._device.fan_speed
        percentage = ordered_list_item_to_percentage(ORDERED_NAMED_FAN_SPEEDS, speed)
        _LOGGER.debug("Current percentage is %s", percentage)
        return percentage

    async def async_turn_on(
        self,
        speed: Optional[str] = None,
        percentage: Optional[int] = None,
        preset_mode: Optional[str] = None,
        **kwargs: Any,
    ):
        """Turn the entity on."""
        _LOGGER.debug("Current powering on")
        power = await self._device.set({PROPERTY_POWER: True})
        _LOGGER.debug("Current state is %s", power)
        if speed:
            await self.async_set_speed(speed)
        if percentage:
            await self.async_set_percentage(percentage)
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        curr_state = self._device.power
        _LOGGER.debug("Current state after on is %s", curr_state)

    async def async_turn_off(self):
        """Turn the entity off."""
        _LOGGER.debug("Current powering off")
        power = await self._device.set({PROPERTY_POWER: False})
        _LOGGER.debug("Current state is %s", power)
        curr_state = self._device.power
        _LOGGER.debug("Current state after off is %s", curr_state)
        return curr_state

    async def async_toggle(self) -> None:
        """Toggle the fan."""
        state = self._device.power()
        if not state:
            await self.async_turn_on()
        else:
            await self.async_turn_on()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        if preset_mode is not None:
            await self._device.set({erv.PROPERTY_FAN_SPEED: preset_mode})
        else:
            await self.async_turn_off()

    async def async_set_speed(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        if percentage != 0:
            named_speed = percentage_to_ordered_list_item(
                ORDERED_NAMED_FAN_SPEEDS, percentage
            )
            await self.async_set_preset_mode(named_speed)
        else:
            await self.async_turn_off()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        if percentage != 0:
            named_speed = percentage_to_ordered_list_item(
                ORDERED_NAMED_FAN_SPEEDS, percentage
            )
            await self.async_set_preset_mode(named_speed)
        else:
            await self.async_turn_off()
