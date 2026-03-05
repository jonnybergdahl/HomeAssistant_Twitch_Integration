"""Support for the Twitch stream status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TwitchConfigEntry, TwitchCoordinator, TwitchUpdate

ATTR_SUBSCRIPTION = "subscribed"
ATTR_SUBSCRIPTION_GIFTED = "subscription_is_gifted"
ATTR_SUBSCRIPTION_TIER = "subscription_tier"
ATTR_FOLLOW = "following"
ATTR_FOLLOW_SINCE = "following_since"
ATTR_FOLLOWING = "followers"
STATE_OFFLINE = "offline"
STATE_STREAMING = "streaming"

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TwitchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Initialize entries."""
    coordinator = entry.runtime_data
    known_ids: set[str] = set(coordinator.data)

    async_add_entities(
        TwitchSensor(coordinator, channel_id) for channel_id in coordinator.data
    )

    @callback
    def _async_add_new_channels(new_channel_ids: list[str]) -> None:
        new = [cid for cid in new_channel_ids if cid not in known_ids]
        if new:
            known_ids.update(new)
            async_add_entities(
                TwitchSensor(coordinator, cid) for cid in new
            )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_new_channels_{entry.entry_id}",
            _async_add_new_channels,
        )
    )


class TwitchSensor(CoordinatorEntity[TwitchCoordinator], SensorEntity):
    """Representation of a Twitch channel."""

    _attr_translation_key = "channel"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STATE_OFFLINE, STATE_STREAMING]

    def __init__(self, coordinator: TwitchCoordinator, channel_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.channel_id = channel_id
        self._attr_unique_id = channel_id
        self._attr_name = self.channel.name

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.channel_id in self.coordinator.data

    @property
    def channel(self) -> TwitchUpdate:
        """Return the channel data."""
        return self.coordinator.data[self.channel_id]

    _attr_icon = "mdi:twitch"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return STATE_STREAMING if self.channel.is_streaming else STATE_OFFLINE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        channel = self.channel
        resp: dict[str, Any] = {
            ATTR_FOLLOWING: channel.followers,
        }
        if channel.subscribed is not None:
            resp[ATTR_SUBSCRIPTION] = channel.subscribed
            if channel.subscribed:
                resp[ATTR_SUBSCRIPTION_GIFTED] = channel.subscription_gifted
                resp[ATTR_SUBSCRIPTION_TIER] = channel.subscription_tier
        resp[ATTR_FOLLOW] = channel.follows
        if channel.follows:
            resp[ATTR_FOLLOW_SINCE] = channel.following_since
        return resp

    @property
    def entity_picture(self) -> str:
        """Return the channel profile picture."""
        return self.channel.picture
