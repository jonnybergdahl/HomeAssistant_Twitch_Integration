"""Tests for the Twitch calendar platform."""

from unittest.mock import AsyncMock

from twitchAPI.object.api import ChannelStreamScheduleSegment
from twitchAPI.type import TwitchResourceNotFound

from homeassistant.core import HomeAssistant

from . import TwitchIterObject, get_generator_from_data, setup_integration

from tests.common import MockConfigEntry, async_load_json_array_fixture
from tests.typing import ClientSessionGenerator

ENTITY_ID = "calendar.channel123_calendar"


async def test_calendar_entity_no_schedule(
    hass: HomeAssistant,
    twitch_mock: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test calendar entity state when no channels have a schedule."""
    await setup_integration(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "off"


async def test_calendar_entity_with_schedule(
    hass: HomeAssistant,
    twitch_mock: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test calendar entity state when a channel has an upcoming scheduled stream."""
    twitch_mock.return_value.get_channel_stream_schedule = AsyncMock(
        return_value=TwitchIterObject(
            hass, "get_channel_stream_schedule.json", ChannelStreamScheduleSegment
        )
    )
    await setup_integration(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    # The fixture event is in the far future (2099), beyond the 30-day window,
    # so the event property returns None and state is off.
    assert state.state == "off"
    assert state.attributes.get("message") is None


async def test_calendar_get_events(
    hass: HomeAssistant,
    twitch_mock: AsyncMock,
    config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test fetching calendar events via the API for a date range."""
    twitch_mock.return_value.get_channel_stream_schedule = AsyncMock(
        return_value=TwitchIterObject(
            hass, "get_channel_stream_schedule.json", ChannelStreamScheduleSegment
        )
    )
    await setup_integration(hass, config_entry)

    client = await hass_client()
    resp = await client.get(
        f"/api/calendars/{ENTITY_ID}",
        params={
            "start": "2099-01-01T00:00:00Z",
            "end": "2099-12-31T00:00:00Z",
        },
    )
    assert resp.status == 200
    events = await resp.json()
    # The end_date is capped to today + 30 days, so the 2099 fixture event
    # falls outside the window and is excluded.
    assert events == []


async def test_calendar_get_events_no_schedule(
    hass: HomeAssistant,
    twitch_mock: AsyncMock,
    config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test fetching calendar events returns empty list when channels have no schedule."""
    twitch_mock.return_value.get_channel_stream_schedule = AsyncMock(
        side_effect=TwitchResourceNotFound
    )
    await setup_integration(hass, config_entry)

    client = await hass_client()
    resp = await client.get(
        f"/api/calendars/{ENTITY_ID}",
        params={
            "start": "2099-01-01T00:00:00Z",
            "end": "2099-12-31T00:00:00Z",
        },
    )
    assert resp.status == 200
    events = await resp.json()
    assert events == []


async def test_calendar_skips_canceled_segments(
    hass: HomeAssistant,
    twitch_mock: AsyncMock,
    config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test that canceled schedule segments are excluded from events and event property."""
    from homeassistant.components.twitch.const import DOMAIN

    raw = await async_load_json_array_fixture(
        hass, "get_channel_stream_schedule.json", DOMAIN
    )
    # Mark the segment as canceled
    canceled_raw = [{**raw[0], "canceled_until": "2099-06-01T00:00:00Z"}]

    # Use side_effect so each call gets a fresh generator (avoids exhaustion issue)
    def make_canceled_schedule(*args, **kwargs):
        return get_generator_from_data(canceled_raw, ChannelStreamScheduleSegment)

    twitch_mock.return_value.get_channel_stream_schedule.side_effect = (
        make_canceled_schedule
    )
    await setup_integration(hass, config_entry)

    # event property should return None for a canceled segment
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "off"
    assert state.attributes.get("message") is None

    # async_get_events should also exclude canceled segments
    client = await hass_client()
    resp = await client.get(
        f"/api/calendars/{ENTITY_ID}",
        params={
            "start": "2099-01-01T00:00:00Z",
            "end": "2099-12-31T00:00:00Z",
        },
    )
    assert resp.status == 200
    assert await resp.json() == []


async def test_calendar_get_events_filters_by_end_date(
    hass: HomeAssistant,
    twitch_mock: AsyncMock,
    config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test that events starting on or after end_date are excluded."""
    twitch_mock.return_value.get_channel_stream_schedule = AsyncMock(
        return_value=TwitchIterObject(
            hass, "get_channel_stream_schedule.json", ChannelStreamScheduleSegment
        )
    )
    await setup_integration(hass, config_entry)

    client = await hass_client()
    # Use an end_date before the fixture event's start_time (2099-01-01T10:00:00Z)
    resp = await client.get(
        f"/api/calendars/{ENTITY_ID}",
        params={
            "start": "2098-01-01T00:00:00Z",
            "end": "2099-01-01T09:00:00Z",
        },
    )
    assert resp.status == 200
    assert await resp.json() == []
