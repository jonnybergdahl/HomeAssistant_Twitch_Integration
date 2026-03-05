"""Tests for the Twitch binary sensor platform."""

from unittest.mock import AsyncMock

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
    assert state.attributes["icon"] == "mdi:twitch"
    assert state.attributes["game"] == "Good game"
    assert state.attributes["title"] == "Title"


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
    assert state.attributes["game"] is None
    assert state.attributes["title"] is None
