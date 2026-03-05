"""The tests for an update of the Twitch component."""

from datetime import datetime
from unittest.mock import AsyncMock

from twitchAPI.object.api import FollowedChannel, Stream, UserSubscription
from twitchAPI.type import TwitchAuthorizationException, TwitchResourceNotFound

from homeassistant.components.twitch.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import TwitchIterObject, get_generator_from_data, setup_integration

from tests.common import MockConfigEntry, async_load_json_object_fixture

OWNER_ENTITY_ID = "sensor.channel123"
FOLLOWED_ENTITY_ID = "sensor.channel456"


async def test_offline(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test offline state."""
    twitch_mock.return_value.get_streams = lambda *args, **kwargs: get_generator_from_data(
        [], Stream
    )
    await setup_integration(hass, config_entry)

    sensor_state = hass.states.get(OWNER_ENTITY_ID)
    assert sensor_state.state == "offline"
    assert sensor_state.attributes["icon"] == "mdi:twitch"
    assert sensor_state.attributes["entity_picture"] == "logo.png"


async def test_streaming(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test streaming state."""
    await setup_integration(hass, config_entry)

    sensor_state = hass.states.get(OWNER_ENTITY_ID)
    assert sensor_state.state == "streaming"
    assert sensor_state.attributes["icon"] == "mdi:twitch"
    assert sensor_state.attributes["entity_picture"] == "logo.png"


async def test_oauth_without_sub_and_follow(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test followed channel with no subscription and not following."""
    twitch_mock.return_value.get_followed_channels.return_value = TwitchIterObject(
        hass, "empty_response.json", FollowedChannel
    )
    twitch_mock.return_value.check_user_subscription.side_effect = (
        TwitchResourceNotFound
    )
    await setup_integration(hass, config_entry)

    # Trigger second update to populate slow data (deferred on first refresh)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    sensor_state = hass.states.get(FOLLOWED_ENTITY_ID)
    assert sensor_state.attributes["subscribed"] is False
    assert sensor_state.attributes["following"] is False


async def test_oauth_with_sub(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test followed channel with subscription."""
    twitch_mock.return_value.get_followed_channels.return_value = TwitchIterObject(
        hass, "empty_response.json", FollowedChannel
    )
    subscription = await async_load_json_object_fixture(
        hass, "check_user_subscription_2.json", DOMAIN
    )
    twitch_mock.return_value.check_user_subscription.return_value = UserSubscription(
        **subscription
    )
    await setup_integration(hass, config_entry)

    # Trigger second update to populate slow data (deferred on first refresh)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    sensor_state = hass.states.get(FOLLOWED_ENTITY_ID)
    assert sensor_state.attributes["subscribed"] is True
    assert sensor_state.attributes["subscription_is_gifted"] is False
    assert sensor_state.attributes["subscription_tier"] == 1
    assert sensor_state.attributes["following"] is False


async def test_auth_failed(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test that auth failure triggers reauth flow."""
    twitch_mock.return_value.get_followed_channels.side_effect = (
        TwitchAuthorizationException
    )
    await setup_integration(hass, config_entry)

    # First refresh defers slow data; trigger second update where auth fails
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"


async def test_oauth_with_follow(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test followed channel shows following status."""
    await setup_integration(hass, config_entry)

    # Trigger second update to populate slow data (deferred on first refresh)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    sensor_state = hass.states.get(FOLLOWED_ENTITY_ID)
    assert sensor_state.attributes["following"] is True
    assert sensor_state.attributes["following_since"] == datetime(
        year=2023, month=8, day=1
    )


async def test_owner_attributes(
    hass: HomeAssistant, twitch_mock: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Test owner sensor shows follower and subscriber counts."""
    await setup_integration(hass, config_entry)

    # Trigger second update to populate slow data (deferred on first refresh)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    sensor_state = hass.states.get(OWNER_ENTITY_ID)
    assert sensor_state.attributes["followers"] == 42
    assert sensor_state.attributes["subscriber_count"] == 10
    assert sensor_state.attributes["subscriber_points"] == 25
    # Owner should not have subscription/following attributes
    assert "subscribed" not in sensor_state.attributes
    assert "following" not in sensor_state.attributes
