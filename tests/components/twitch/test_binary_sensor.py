"""Tests for the Twitch binary sensor platform."""

from datetime import datetime
from unittest.mock import AsyncMock

from dateutil.tz import tzutc
from twitchAPI.object.api import Stream

from homeassistant.core import HomeAssistant

from . import get_generator_from_data, setup_integration

from tests.common import MockConfigEntry

ENTITY_ID = "binary_sensor.channel123_live"


async def test_live(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test binary sensor state when channel is live."""
    await setup_integration(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["friendly_name"] == "channel123 live"
    assert state.attributes["icon"] == "mdi:video-outline"
    assert state.attributes["game"] == "Good game"
    assert state.attributes["title"] == "Title"
    assert state.attributes["started_at"] == datetime(
        year=2021, month=3, day=10, hour=3, minute=18, second=11, tzinfo=tzutc()
    )
    assert state.attributes["viewers"] == 42
    assert state.attributes["stream_id"] == "stream-abc123"
    assert state.attributes["language"] == "en"
    assert state.attributes["is_mature"] is False
    assert state.attributes["entity_picture"] == "stream-medium.png"


async def test_offline(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test binary sensor state when channel is offline."""
    twitch_mock.return_value.get_streams = lambda *args, **kwargs: get_generator_from_data(
        [], Stream
    )
    await setup_integration(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["icon"] == "mdi:video-off-outline"
    assert "game" not in state.attributes
    assert "title" not in state.attributes
    assert "viewers" not in state.attributes
    assert "stream_id" not in state.attributes
    assert state.attributes["entity_picture"] == "logo.png"
