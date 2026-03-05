"""Configure tests for the Twitch integration."""

from collections.abc import Generator
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitchAPI.object.api import (
    ChannelStreamScheduleSegment,
    FollowedChannel,
    Stream,
    TwitchUser,
    UserSubscription,
)
from twitchAPI.type import TwitchResourceNotFound

from homeassistant.components.application_credentials import (
    DOMAIN as APPLICATION_CREDENTIALS_DOMAIN,
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.components.twitch.const import DOMAIN, OAUTH2_TOKEN, OAUTH_SCOPES
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from . import TwitchIterObject, get_generator

from tests.common import MockConfigEntry, load_json_object_fixture
from tests.test_util.aiohttp import AiohttpClientMocker

CLIENT_ID = "1234"
CLIENT_SECRET = "5678"
TITLE = "Test"


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.twitch.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture(name="scopes")
def mock_scopes() -> list[str]:
    """Fixture to set the scopes present in the OAuth token."""
    return [scope.value for scope in OAUTH_SCOPES]


@pytest.fixture(autouse=True)
async def setup_credentials(hass: HomeAssistant) -> None:
    """Fixture to setup credentials."""
    assert await async_setup_component(hass, APPLICATION_CREDENTIALS_DOMAIN, {})
    await async_import_client_credential(
        hass,
        DOMAIN,
        ClientCredential(CLIENT_ID, CLIENT_SECRET),
        DOMAIN,
    )


@pytest.fixture(name="expires_at")
def mock_expires_at() -> int:
    """Fixture to set the oauth token expiration time."""
    return time.time() + 3600


@pytest.fixture(name="config_entry")
def mock_config_entry(expires_at: int, scopes: list[str]) -> MockConfigEntry:
    """Create Twitch entry in Home Assistant."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=TITLE,
        unique_id="123",
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": "mock-access-token",
                "refresh_token": "mock-refresh-token",
                "expires_at": expires_at,
                "scope": " ".join(scopes),
            },
        },
        options={"channels": ["internetofthings"]},
    )


@pytest.fixture(autouse=True)
def mock_connection(aioclient_mock: AiohttpClientMocker) -> None:
    """Mock Twitch connection."""
    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "refresh_token": "mock-refresh-token",
            "access_token": "mock-access-token",
            "type": "Bearer",
            "expires_in": 60,
        },
    )


@pytest.fixture
def twitch_mock(hass: HomeAssistant) -> Generator[AsyncMock]:
    """Return as fixture to inject other mocks."""
    with (
        patch(
            "homeassistant.components.twitch.Twitch",
            autospec=True,
        ) as mock_client,
        patch(
            "homeassistant.components.twitch.config_flow.Twitch",
            new=mock_client,
        ),
        patch(
            "homeassistant.components.twitch.coordinator.EventSubWebsocket"
        ) as mock_eventsub,
    ):
        # EventSub mock — start() is sync, stop/listen are async
        mock_eventsub.return_value.start = MagicMock()
        mock_eventsub.return_value.stop = AsyncMock()
        mock_eventsub.return_value.listen_stream_online = AsyncMock(return_value="sub_id")
        mock_eventsub.return_value.listen_stream_offline = AsyncMock(return_value="sub_id")
        mock_eventsub.return_value.listen_channel_follow_v2 = AsyncMock(return_value="sub_id")
        mock_eventsub.return_value.listen_channel_subscribe = AsyncMock(return_value="sub_id")
        mock_eventsub.return_value.listen_channel_subscription_end = AsyncMock(return_value="sub_id")
        mock_eventsub.return_value.listen_channel_subscription_gift = AsyncMock(return_value="sub_id")

        # get_users(logins=...) returns followed channels (get_users_2.json)
        # get_users() with no logins returns the current user (get_users.json)
        mock_client.return_value.get_users = lambda *args, **kwargs: (
            get_generator(hass, "get_users_2.json", TwitchUser)
            if kwargs.get("logins")
            else get_generator(hass, "get_users.json", TwitchUser)
        )
        # Factory lambda ensures each call gets a fresh async generator
        mock_client.return_value.get_streams = lambda *args, **kwargs: get_generator(
            hass, "get_followed_streams.json", Stream
        )
        mock_client.return_value.get_followed_channels.return_value = TwitchIterObject(
            hass, "get_followed_channels.json", FollowedChannel
        )
        mock_client.return_value.check_user_subscription.return_value = (
            UserSubscription(
                **load_json_object_fixture("check_user_subscription.json", DOMAIN)
            )
        )
        mock_followers = MagicMock()
        mock_followers.total = 42
        mock_client.return_value.get_channel_followers = AsyncMock(
            return_value=mock_followers
        )
        mock_broadcaster_subs = MagicMock()
        mock_broadcaster_subs.total = 10
        mock_broadcaster_subs.points = 25
        mock_client.return_value.get_broadcaster_subscriptions = AsyncMock(
            return_value=mock_broadcaster_subs
        )
        mock_client.return_value.has_required_auth.return_value = True
        mock_client.return_value.get_channel_stream_schedule = AsyncMock(
            side_effect=TwitchResourceNotFound
        )
        yield mock_client
