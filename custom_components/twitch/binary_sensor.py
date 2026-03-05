"""Support for Twitch live status as a binary sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TwitchConfigEntry, TwitchCoordinator, TwitchUpdate

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TwitchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Initialize binary sensor entries."""
    coordinator = entry.runtime_data
    known_ids: set[str] = set(coordinator.data)

    async_add_entities(
        TwitchLiveSensor(coordinator, channel_id) for channel_id in coordinator.data
    )

    @callback
    def _async_add_new_channels(new_channel_ids: list[str]) -> None:
        new = [cid for cid in new_channel_ids if cid not in known_ids]
        if new:
            known_ids.update(new)
            async_add_entities(
                TwitchLiveSensor(coordinator, cid) for cid in new
            )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_new_channels_{entry.entry_id}",
            _async_add_new_channels,
        )
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
        return "mdi:video-outline" if self.channel.is_streaming else "mdi:video-off-outline"

    @property
    def is_on(self) -> bool:
        """Return true when the channel is live."""
        return self.channel.is_streaming

    @property
    def entity_picture(self) -> str:
        """Return the stream thumbnail when live, channel picture otherwise."""
        if self.channel.is_streaming and self.channel.stream_picture:
            return self.channel.stream_picture
        return self.channel.picture

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        channel = self.channel
        if not channel.is_streaming:
            return {}
        return {
            "game": channel.game,
            "title": channel.title,
            "started_at": channel.started_at,
            "viewers": channel.viewers,
            "stream_id": channel.stream_id,
            "language": channel.language,
            "is_mature": channel.is_mature,
        }
