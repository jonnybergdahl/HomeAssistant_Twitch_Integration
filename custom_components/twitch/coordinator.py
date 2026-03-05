"""Define a class to manage fetching Twitch data."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.helper import first
from twitchAPI.object.api import (
    FollowedChannel,
    Stream,
    TwitchUser,
    UserSubscription,
)
from twitchAPI.object.eventsub import StreamOfflineEvent, StreamOnlineEvent
from twitchAPI.twitch import Twitch
from twitchAPI.type import (
    EventSubSubscriptionError,
    TwitchAPIException,
    TwitchAuthorizationException,
    TwitchResourceNotFound,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_ALL_CHANNELS, CONF_CHANNELS, DOMAIN, LOGGER, OAUTH_SCOPES

type TwitchConfigEntry = ConfigEntry[TwitchCoordinator]

_SLOW_UPDATE_INTERVAL = timedelta(hours=1)


def chunk_list(lst: list, chunk_size: int) -> list[list]:
    """Split a list into chunks of chunk_size."""
    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]


@dataclass
class _TwitchSlowData:
    """Infrequently changing data for a single channel."""

    followers: int
    subscribed: bool | None
    subscription_gifted: bool | None
    subscription_tier: int | None
    follows: bool
    following_since: datetime | None


@dataclass
class TwitchUpdate:
    """Class for holding Twitch data."""

    name: str
    followers: int
    is_streaming: bool
    game: str | None
    title: str | None
    started_at: datetime | None
    stream_picture: str | None
    picture: str
    subscribed: bool | None
    subscription_gifted: bool | None
    subscription_tier: int | None
    follows: bool
    following_since: datetime | None
    viewers: int | None
    stream_id: str | None
    language: str | None
    is_mature: bool | None


class TwitchCoordinator(DataUpdateCoordinator[dict[str, TwitchUpdate]]):
    """Class to manage fetching Twitch data."""

    config_entry: TwitchConfigEntry
    users: list[TwitchUser]
    current_user: TwitchUser

    def __init__(
        self,
        hass: HomeAssistant,
        twitch: Twitch,
        session: OAuth2Session,
        entry: TwitchConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.twitch = twitch
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
            config_entry=entry,
        )
        self.session = session
        self._slow_data: dict[str, _TwitchSlowData] = {}
        self._last_slow_update: datetime | None = None
        self._slow_update_deferred = False
        self._stream_data: dict[str, Stream] = {}
        self._eventsub: EventSubWebsocket | None = None

    async def _async_setup(self) -> None:
        """Set up the coordinator, fetching users and initial stream data."""
        channels = self.config_entry.options[CONF_CHANNELS]
        LOGGER.debug("Setting up coordinator for %d channel(s): %s", len(channels), channels)
        self.users = []
        for chunk in chunk_list(channels, 100):
            self.users.extend(
                [channel async for channel in self.twitch.get_users(logins=chunk)]
            )
        if not (user := await first(self.twitch.get_users())):
            raise UpdateFailed("Logged in user not found")
        self.current_user = user
        self.users.append(self.current_user)
        LOGGER.debug(
            "Coordinator setup complete; tracking %d user(s), current user: %s",
            len(self.users),
            self.current_user.login,
        )

        # Fetch initial stream status for all tracked channels
        all_user_ids = [u.id for u in self.users]
        for chunk in chunk_list(all_user_ids, 100):
            async for stream in self.twitch.get_streams(user_id=chunk):
                self._stream_data[stream.user_id] = stream

    async def async_start_eventsub(self) -> None:
        """Start EventSub WebSocket for real-time stream status updates."""
        # start() is sync with a busy-wait loop so run it in the executor.
        # Don't pass callback_loop; the library's create_task call is not
        # thread-safe. Instead, callbacks run on the socket's own loop and
        # schedule HA work via asyncio.run_coroutine_threadsafe.
        self._eventsub = EventSubWebsocket(self.twitch)
        await self.hass.async_add_executor_job(self._eventsub.start)

        try:
            await asyncio.gather(
                *(
                    coro
                    for user in self.users
                    for coro in (
                        self._eventsub.listen_stream_online(
                            user.id, self._async_on_stream_online
                        ),
                        self._eventsub.listen_stream_offline(
                            user.id, self._async_on_stream_offline
                        ),
                    )
                )
            )
        except EventSubSubscriptionError:
            LOGGER.warning(
                "EventSub subscription limit exceeded; falling back to polling"
            )
            await self._eventsub.stop()
            self._eventsub = None
            return

        LOGGER.debug("EventSub WebSocket started for %d channel(s)", len(self.users))

    async def async_shutdown(self) -> None:
        """Stop EventSub WebSocket."""
        if self._eventsub is not None:
            await self._eventsub.stop()
            self._eventsub = None

    async def _async_on_stream_online(self, event: StreamOnlineEvent) -> None:
        """Handle stream.online event from EventSub (runs on socket thread)."""
        LOGGER.debug("Stream online: %s", event.event.broadcaster_user_name)
        asyncio.run_coroutine_threadsafe(
            self._async_process_stream_online(event.event.broadcaster_user_id),
            self.hass.loop,
        )

    async def _async_process_stream_online(self, broadcaster_id: str) -> None:
        """Fetch stream data and push coordinator update."""
        stream = await first(self.twitch.get_streams(user_id=[broadcaster_id]))
        if stream is not None:
            self._stream_data[broadcaster_id] = stream
        self.async_set_updated_data(self._build_data())

    async def _async_on_stream_offline(self, event: StreamOfflineEvent) -> None:
        """Handle stream.offline event from EventSub (runs on socket thread)."""
        LOGGER.debug("Stream offline: %s", event.event.broadcaster_user_name)
        asyncio.run_coroutine_threadsafe(
            self._async_process_stream_offline(event.event.broadcaster_user_id),
            self.hass.loop,
        )

    async def _async_process_stream_offline(self, broadcaster_id: str) -> None:
        """Remove stream data and push coordinator update."""
        self._stream_data.pop(broadcaster_id, None)
        self.async_set_updated_data(self._build_data())

    def _build_data(self) -> dict[str, TwitchUpdate]:
        """Build TwitchUpdate dict from cached stream and slow data."""
        data: dict[str, TwitchUpdate] = {}
        for channel in self.users:
            stream = self._stream_data.get(channel.id)
            slow = self._slow_data.get(channel.id)
            data[channel.id] = TwitchUpdate(
                name=channel.display_name,
                followers=slow.followers if slow else 0,
                is_streaming=bool(stream),
                game=stream.game_name if stream else None,
                title=stream.title if stream else None,
                started_at=stream.started_at if stream else None,
                stream_picture=stream.thumbnail_url.format(width=640, height=360)
                if stream
                else None,
                picture=channel.profile_image_url,
                subscribed=slow.subscribed if slow else None,
                subscription_gifted=slow.subscription_gifted if slow else None,
                subscription_tier=slow.subscription_tier if slow else None,
                follows=slow.follows if slow else False,
                following_since=slow.following_since if slow else None,
                viewers=stream.viewer_count if stream else None,
                stream_id=stream.id if stream else None,
                language=stream.language if stream else None,
                is_mature=stream.is_mature if stream else None,
            )
        return data

    async def _async_update_slow(self) -> None:
        """Fetch infrequently changing data: follower counts, subscriptions, follows."""
        LOGGER.debug("Running slow update for %d channel(s)", len(self.users))
        follows: dict[str, FollowedChannel] = {
            f.broadcaster_id: f
            async for f in await self.twitch.get_followed_channels(
                user_id=self.current_user.id, first=100
            )
        }

        # Auto-discover new followed channels when tracking all
        if self.config_entry.options.get(CONF_ALL_CHANNELS, False):
            tracked_logins = {u.login for u in self.users}
            new_logins = [
                f.broadcaster_login
                for f in follows.values()
                if f.broadcaster_login not in tracked_logins
            ]
            if new_logins:
                LOGGER.debug("Discovered %d new followed channel(s): %s", len(new_logins), new_logins)
                new_users: list[TwitchUser] = []
                for chunk in chunk_list(new_logins, 100):
                    new_users.extend(
                        [u async for u in self.twitch.get_users(logins=chunk)]
                    )
                self.users.extend(new_users)
                # Fetch initial stream status for new channels
                new_ids = [u.id for u in new_users]
                for chunk in chunk_list(new_ids, 100):
                    async for stream in self.twitch.get_streams(user_id=chunk):
                        self._stream_data[stream.user_id] = stream
                # Update stored channel list
                all_logins = [
                    u.login for u in self.users if u.id != self.current_user.id
                ]
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    options={**self.config_entry.options, CONF_CHANNELS: all_logins},
                )
                async_dispatcher_send(
                    self.hass,
                    f"{DOMAIN}_new_channels_{self.config_entry.entry_id}",
                    [u.id for u in new_users],
                )

        for channel in self.users:
            LOGGER.debug("Fetching slow data for channel: %s", channel.display_name)
            followers = await self.twitch.get_channel_followers(channel.id)
            follow = follows.get(channel.id)
            sub: UserSubscription | None = None
            if channel.id != self.current_user.id:
                try:
                    LOGGER.debug(
                        "Checking subscription: user %s (%s) -> broadcaster %s (%s)",
                        self.current_user.login,
                        self.current_user.id,
                        channel.login,
                        channel.id,
                    )
                    sub = await self.twitch.check_user_subscription(
                        user_id=self.current_user.id, broadcaster_id=channel.id
                    )
                    LOGGER.debug("Subscribed to %s (tier %s)", channel.display_name, sub.tier)
                except TwitchResourceNotFound:
                    LOGGER.debug("User is not subscribed to %s", channel.display_name)
                except TwitchAPIException as exc:
                    LOGGER.error("Error response on check_user_subscription: %s", exc)

            self._slow_data[channel.id] = _TwitchSlowData(
                followers=followers.total,
                subscribed=bool(sub),
                subscription_gifted=sub.is_gift if sub else None,
                subscription_tier={"1000": 1, "2000": 2, "3000": 3}.get(sub.tier)
                if sub
                else None,
                follows=bool(follow),
                following_since=follow.followed_at if follow else None,
            )
        self._last_slow_update = datetime.now(UTC)
        LOGGER.debug("Slow update complete")

    async def _async_update_data(self) -> dict[str, TwitchUpdate]:
        """Fetch periodic data: slow data and viewer count refreshes for live channels."""
        try:
            await self.session.async_ensure_token_valid()
            await self.twitch.set_user_authentication(
                self.session.token["access_token"],
                OAUTH_SCOPES,
                self.session.token["refresh_token"],
                False,
            )

            # Defer the slow update on the first call so it doesn't block
            # startup. It will run on the next polling cycle instead.
            now = datetime.now(UTC)
            if self._last_slow_update is None and not self._slow_update_deferred:
                self._slow_update_deferred = True
            elif (
                self._last_slow_update is None
                or now - self._last_slow_update >= _SLOW_UPDATE_INTERVAL
            ):
                await self._async_update_slow()

            # Refresh viewer counts for currently live channels
            live_ids = list(self._stream_data.keys())
            if live_ids:
                for chunk in chunk_list(live_ids, 100):
                    async for stream in self.twitch.get_streams(user_id=chunk):
                        self._stream_data[stream.user_id] = stream
        except TwitchAuthorizationException as err:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"oauth_token_expired_{self.config_entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="oauth_token_expired",
                translation_placeholders={"title": self.config_entry.title},
            )
            raise ConfigEntryAuthFailed("Twitch authorization failed") from err

        return self._build_data()
