"""Const for Twitch."""

import logging

from twitchAPI.twitch import AuthScope

from homeassistant.const import Platform

LOGGER = logging.getLogger(__package__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

OAUTH2_AUTHORIZE = "https://id.twitch.tv/oauth2/authorize"
OAUTH2_TOKEN = "https://id.twitch.tv/oauth2/token"

CONF_REFRESH_TOKEN = "refresh_token"

DOMAIN = "twitch"
CONF_ALL_CHANNELS = "all_channels"
CONF_CHANNELS = "channels"
CONF_TOKEN = "token"

OAUTH_SCOPES = [
    AuthScope.CHANNEL_READ_SUBSCRIPTIONS,
    AuthScope.MODERATOR_READ_FOLLOWERS,
    AuthScope.USER_READ_SUBSCRIPTIONS,
    AuthScope.USER_READ_FOLLOWS,
]

# Twitch allows max 10 subscriptions per WebSocket connection and 3 connections total.
# The owner uses 1 connection with 6 subscriptions (online + offline + follow + subscribe + sub_end + sub_gift).
# Each followed channel needs 2 subscriptions (online + offline).
# We use up to 2 additional connections for channels (5 channels each = 10 subscriptions).
# Max with EventSub: 2 connections × 5 channels = 10 channels. Beyond that, we fall back to polling.
EVENTSUB_MAX_CHANNELS = 10
