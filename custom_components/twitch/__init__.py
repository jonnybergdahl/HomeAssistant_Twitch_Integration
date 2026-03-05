"""The Twitch component."""

from __future__ import annotations

from typing import cast

from aiohttp.client_exceptions import ClientError, ClientResponseError
from twitchAPI.twitch import Twitch
from twitchAPI.type import InvalidTokenException

from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.config_entry_oauth2_flow import (
    ImplementationUnavailableError,
    LocalOAuth2Implementation,
    OAuth2Session,
    async_get_config_entry_implementation,
)

from .const import DOMAIN, EVENTSUB_MAX_CHANNELS, OAUTH_SCOPES, PLATFORMS
from .coordinator import TwitchConfigEntry, TwitchCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: TwitchConfigEntry) -> bool:
    """Set up Twitch from a config entry."""
    try:
        implementation = cast(
            LocalOAuth2Implementation,
            await async_get_config_entry_implementation(hass, entry),
        )
    except (ImplementationUnavailableError, ValueError) as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="oauth2_implementation_unavailable",
        ) from err
    session = OAuth2Session(hass, entry, implementation)
    try:
        await session.async_ensure_token_valid()
    except ClientResponseError as err:
        if 400 <= err.status < 500:
            ir.async_create_issue(
                hass,
                DOMAIN,
                f"oauth_token_expired_{entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="oauth_token_expired",
                translation_placeholders={"title": entry.title},
            )
            raise ConfigEntryAuthFailed(
                "OAuth session is not valid, reauth required"
            ) from err
        raise ConfigEntryNotReady from err
    except ClientError as err:
        raise ConfigEntryNotReady from err

    ir.async_delete_issue(hass, DOMAIN, f"oauth_token_expired_{entry.entry_id}")

    access_token = entry.data[CONF_TOKEN][CONF_ACCESS_TOKEN]
    client = Twitch(
        app_id=implementation.client_id,
        authenticate_app=False,
    )
    client.auto_refresh_auth = False
    try:
        await client.set_user_authentication(access_token, scope=OAUTH_SCOPES)
    except InvalidTokenException as err:
        raise ConfigEntryAuthFailed("Invalid access token") from err

    coordinator = TwitchCoordinator(hass, client, session, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if len(coordinator.users) <= EVENTSUB_MAX_CHANNELS:
        entry.async_create_background_task(
            hass, coordinator.async_start_eventsub(), "twitch_eventsub_start"
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: TwitchConfigEntry) -> bool:
    """Unload Twitch config entry."""
    await entry.runtime_data.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: TwitchConfigEntry) -> None:
    """Clean up issues when a config entry is removed."""
    ir.async_delete_issue(hass, DOMAIN, f"oauth_token_expired_{entry.entry_id}")
