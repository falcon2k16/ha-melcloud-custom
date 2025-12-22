"""Platform for fan - erv integration."""

from __future__ import annotations

import logging
from typing import Any

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

    async def async_update(self) -> None:
        """Update state from the coordinator."""
        await self.api.coordinator.async_request_refresh()

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
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if not self._device.power:
            return 0
        speed = self._device.fan_speed
        if speed is None:
            return None
        percentage = ordered_list_item_to_percentage(ORDERED_NAMED_FAN_SPEEDS, speed)
        _LOGGER.debug("Current percentage is %s", percentage)
        return percentage

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the entity on."""
        _LOGGER.debug("Powering on")

        # Build the set dictionary with all changes at once
        props = {PROPERTY_POWER: True}

        # Determine the fan speed to set
        if preset_mode is not None:
            props[erv.PROPERTY_FAN_SPEED] = preset_mode
        elif percentage is not None and percentage > 0:
            named_speed = percentage_to_ordered_list_item(
                ORDERED_NAMED_FAN_SPEEDS, percentage
            )
            props[erv.PROPERTY_FAN_SPEED] = named_speed

        # Apply all changes in a single API call
        await self._device.set(props)
        await self.api.coordinator.async_request_refresh()
        _LOGGER.debug("Power state after turn on: %s", self._device.power)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        _LOGGER.debug("Powering off")
        await self._device.set({PROPERTY_POWER: False})
        await self.api.coordinator.async_request_refresh()
        _LOGGER.debug("Power state after turn off: %s", self._device.power)

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the fan."""
        if self._device.power:
            await self.async_turn_off()
        else:
            await self.async_turn_on()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        _LOGGER.debug("Setting preset mode to: %s", preset_mode)
        props = {erv.PROPERTY_FAN_SPEED: preset_mode}

        # Ensure the fan is on when setting a preset mode
        if not self._device.power:
            props[PROPERTY_POWER] = True

        await self._device.set(props)
        await self.api.coordinator.async_request_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        _LOGGER.debug("Setting speed percentage to: %s", percentage)

        if percentage == 0:
            await self.async_turn_off()
            return

        # Convert percentage to named speed
        named_speed = percentage_to_ordered_list_item(
            ORDERED_NAMED_FAN_SPEEDS, percentage
        )
        await self.async_set_preset_mode(named_speed)
