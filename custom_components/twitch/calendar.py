"""Support for Twitch stream schedules as calendar events."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from twitchAPI.object.api import ChannelStreamScheduleSegment
from twitchAPI.type import TwitchResourceNotFound

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .coordinator import TwitchConfigEntry, TwitchCoordinator, TwitchUpdate

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TwitchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Initialize a single Twitch calendar entity from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities([TwitchCalendarEntity(coordinator)])


def _segment_to_event(
    segment: ChannelStreamScheduleSegment, channel_name: str
) -> CalendarEvent:
    """Convert a Twitch schedule segment to a CalendarEvent."""
    summary = f"{channel_name}: {segment.title}" if segment.title else channel_name
    return CalendarEvent(
        summary=summary,
        start=segment.start_time,
        end=segment.end_time,
        description=segment.category.name if segment.category else None,
    )


class TwitchCalendarEntity(CoordinatorEntity[TwitchCoordinator], CalendarEntity):
    """A single calendar showing scheduled streams for all tracked Twitch channels."""

    def __init__(self, coordinator: TwitchCoordinator) -> None:
        """Initialize the calendar entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_calendar"
        self._attr_name = f"{coordinator.current_user.display_name} Calendar"
        self._schedule: dict[str, list[ChannelStreamScheduleSegment]] = {}

    async def async_added_to_hass(self) -> None:
        """Fetch schedules on startup and set up hourly refresh."""
        await super().async_added_to_hass()
        await self._async_fetch_schedules()
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._handle_schedule_interval,
                timedelta(hours=1),
            )
        )

    @callback
    def _handle_schedule_interval(self, _now: datetime) -> None:
        """Trigger a schedule refresh on the hourly timer."""
        self.hass.async_create_task(self._async_fetch_schedules())

    async def _async_fetch_schedules(self) -> None:
        """Fetch stream schedules for all tracked channels in parallel."""
        cutoff = dt_util.utcnow() + timedelta(days=30)

        async def _fetch(
            channel_id: str, channel: TwitchUpdate
        ) -> tuple[str, list[ChannelStreamScheduleSegment]]:
            segments: list[ChannelStreamScheduleSegment] = []
            try:
                async with asyncio.timeout(30):
                    schedule_result = (
                        await self.coordinator.twitch.get_channel_stream_schedule(
                            broadcaster_id=channel_id,
                            first=25,
                        )
                    )
                    async for segment in schedule_result:
                        if segment.start_time > cutoff:
                            break
                        segments.append(segment)
            except TwitchResourceNotFound:
                pass
            except Exception:  # noqa: BLE001
                pass
            return channel_id, segments

        results = await asyncio.gather(
            *[
                _fetch(channel_id, channel)
                for channel_id, channel in self.coordinator.data.items()
            ]
        )
        self._schedule = dict(results)
        self.async_write_ha_state()

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming or currently active stream across all channels."""
        now = dt_util.utcnow()
        upcoming: list[tuple[datetime, CalendarEvent]] = []
        for channel_id, channel in self.coordinator.data.items():
            for segment in self._schedule.get(channel_id, []):
                if segment.canceled_until is not None:
                    continue
                if segment.end_time is None:
                    continue
                if segment.end_time > now:
                    upcoming.append(
                        (segment.start_time, _segment_to_event(segment, channel.name))
                    )
        if not upcoming:
            return None
        upcoming.sort(key=lambda x: x[0])
        return upcoming[0][1]

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range for all tracked channels."""
        end_date = min(end_date, dt_util.utcnow() + timedelta(days=30))

        async def _fetch_channel(
            channel_id: str, channel: TwitchUpdate
        ) -> list[CalendarEvent]:
            events: list[CalendarEvent] = []
            try:
                async with asyncio.timeout(30):
                    schedule = await self.coordinator.twitch.get_channel_stream_schedule(
                        broadcaster_id=channel_id,
                        start_time=start_date,
                        first=25,
                    )
                    async for segment in schedule:
                        if segment.start_time >= end_date:
                            break
                        if segment.canceled_until is not None:
                            continue
                        if segment.end_time is None:
                            continue
                        events.append(_segment_to_event(segment, channel.name))
            except TwitchResourceNotFound:
                pass
            except Exception:  # noqa: BLE001
                pass
            return events

        results = await asyncio.gather(
            *[
                _fetch_channel(channel_id, channel)
                for channel_id, channel in self.coordinator.data.items()
            ]
        )
        return sorted(
            [event for channel_events in results for event in channel_events],
            key=lambda e: e.start,
        )
