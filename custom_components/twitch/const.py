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

OAUTH_SCOPES = [
    AuthScope.CHANNEL_READ_SUBSCRIPTIONS,
    AuthScope.MODERATOR_READ_FOLLOWERS,
    AuthScope.USER_READ_SUBSCRIPTIONS,
    AuthScope.USER_READ_FOLLOWS,
]

# Twitch allows max 10 subscriptions per WebSocket and 3 connections (30 total).
# The owner always uses 6 (online + offline + follow + subscribe + sub_end + sub_gift).
# Each followed channel needs 2 subscriptions (online + offline).
# Theoretical max: (30 - 6) / 2 = 12, but we use 10 for safety margin.
EVENTSUB_MAX_CHANNELS = 10
