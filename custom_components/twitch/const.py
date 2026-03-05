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

OAUTH_SCOPES = [AuthScope.USER_READ_SUBSCRIPTIONS, AuthScope.USER_READ_FOLLOWS]

# Twitch allows max 10 subscriptions per WebSocket and 3 connections.
# Each channel needs 2 subscriptions (online + offline), so max 5 channels per
# connection and 15 channels total. Beyond that we fall back to polling.
EVENTSUB_MAX_CHANNELS = 5
