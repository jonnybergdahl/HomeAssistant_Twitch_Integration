"""Support for Twitch live status as a binary sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import TwitchConfigEntry, TwitchCoordinator, TwitchUpdate

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TwitchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Initialize binary sensor entries."""
    coordinator = entry.runtime_data

    async_add_entities(
        TwitchLiveSensor(coordinator, channel_id) for channel_id in coordinator.data
    )


class TwitchLiveSensor(CoordinatorEntity[TwitchCoordinator], BinarySensorEntity):
    """Binary sensor representing whether a Twitch channel is currently live."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: TwitchCoordinator, channel_id: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.channel_id = channel_id
        self._attr_unique_id = f"{channel_id}_live"
        self._attr_name = f"{self.channel.name} live"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.channel_id in self.coordinator.data

    @property
    def channel(self) -> TwitchUpdate:
        """Return the channel data."""
        return self.coordinator.data[self.channel_id]

    @property
    def icon(self) -> str:
        """Return the icon based on live status."""
        return "mdi:twitch" if self.channel.is_streaming else "mdi:video-off-outline"

    @property
    def is_on(self) -> bool:
        """Return true when the channel is live."""
        return self.channel.is_streaming

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "game": self.channel.game,
            "title": self.channel.title,
        }
