"""Config flow for Twitch."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, cast

import voluptuous as vol
from twitchAPI.helper import first
from twitchAPI.twitch import Twitch

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TOKEN
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.config_entry_oauth2_flow import (
    LocalOAuth2Implementation,
    async_get_config_entry_implementation,
)
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import CONF_ALL_CHANNELS, CONF_CHANNELS, DOMAIN, LOGGER, OAUTH_SCOPES


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Twitch OAuth2 authentication."""

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize flow."""
        super().__init__()
        self.data: dict[str, Any] = {}
        self._user_name: str = ""
        self._current_user_login: str = ""
        self._followed_channels: list[str] = []

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {"scope": " ".join([scope.value for scope in OAUTH_SCOPES])}

    async def async_oauth_create_entry(
        self,
        data: dict[str, Any],
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        implementation = cast(
            LocalOAuth2Implementation,
            self.flow_impl,
        )

        client = Twitch(
            app_id=implementation.client_id,
            authenticate_app=False,
        )
        client.auto_refresh_auth = False
        await client.set_user_authentication(
            data[CONF_TOKEN][CONF_ACCESS_TOKEN], scope=OAUTH_SCOPES
        )
        user = await first(client.get_users())
        assert user

        user_id = user.id

        await self.async_set_unique_id(user_id)
        if self.source != SOURCE_REAUTH:
            self._abort_if_unique_id_configured()

            self.data = data
            self._user_name = user.display_name
            self._current_user_login = user.login or ""
            self._followed_channels = [
                channel.broadcaster_login
                async for channel in await client.get_followed_channels(user_id)
            ]
            return await self.async_step_channels()

        reauth_entry = self._get_reauth_entry()
        self._abort_if_unique_id_mismatch(
            reason="wrong_account",
            description_placeholders={
                "title": reauth_entry.title,
                "username": str(reauth_entry.unique_id),
            },
        )

        new_channels = reauth_entry.options[CONF_CHANNELS]
        # Since we could not get all channels at import, we do it at the reauth
        # immediately after.
        if "imported" in reauth_entry.data:
            channels = [
                channel.broadcaster_login
                async for channel in await client.get_followed_channels(user_id)
            ]
            options = list(set(channels) - set(new_channels))
            new_channels = [*new_channels, *options]

        return self.async_update_reload_and_abort(
            reauth_entry,
            data=data,
            options={CONF_CHANNELS: new_channels},
        )

    async def async_step_channels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether to add all followed channels or select specific ones."""
        if user_input is None:
            return self.async_show_form(
                step_id="channels",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_ALL_CHANNELS, default=True): BooleanSelector(),
                    }
                ),
            )

        if user_input[CONF_ALL_CHANNELS]:
            return self.async_create_entry(
                title=self._user_name,
                data=self.data,
                options={
                    CONF_ALL_CHANNELS: True,
                    CONF_CHANNELS: self._followed_channels,
                },
            )

        return await self.async_step_select_channels()

    async def async_step_select_channels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle specific channel selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_CHANNELS]:
                return self.async_create_entry(
                    title=self._user_name,
                    data=self.data,
                    options={
                        CONF_ALL_CHANNELS: False,
                        CONF_CHANNELS: user_input[CONF_CHANNELS],
                    },
                )
            errors[CONF_CHANNELS] = "no_channels_selected"

        # Include the authenticated user's own channel in the options even if
        # they don't follow themselves; the coordinator always monitors it.
        channel_options = list(self._followed_channels)
        if (
            self._current_user_login
            and self._current_user_login not in channel_options
        ):
            channel_options.insert(0, self._current_user_login)

        options = [SelectOptionDict(value=ch, label=ch) for ch in channel_options]
        default_channels = (
            [self._current_user_login] if self._current_user_login else []
        )
        return self.async_show_form(
            step_id="select_channels",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CHANNELS, default=default_channels
                    ): SelectSelector(
                        SelectSelectorConfig(options=options, multiple=True)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration to update the channel selection."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_CHANNELS]:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    options={
                        CONF_ALL_CHANNELS: False,
                        CONF_CHANNELS: user_input[CONF_CHANNELS],
                    },
                )
            errors[CONF_CHANNELS] = "no_channels_selected"

        implementation = cast(
            LocalOAuth2Implementation,
            await async_get_config_entry_implementation(self.hass, reconfigure_entry),
        )
        client = Twitch(app_id=implementation.client_id, authenticate_app=False)
        client.auto_refresh_auth = False
        await client.set_user_authentication(
            reconfigure_entry.data[CONF_TOKEN][CONF_ACCESS_TOKEN],
            scope=OAUTH_SCOPES,
        )
        user = await first(client.get_users())
        assert user

        followed_channels = [
            channel.broadcaster_login
            async for channel in await client.get_followed_channels(user.id)
        ]

        channel_options = list(followed_channels)
        if user.login and user.login not in channel_options:
            channel_options.insert(0, user.login)

        current_channels = reconfigure_entry.options.get(CONF_CHANNELS, [])
        options = [
            SelectOptionDict(value=ch, label=ch) for ch in channel_options
        ]
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CHANNELS, default=list(current_channels)
                    ): SelectSelector(
                        SelectSelectorConfig(options=options, multiple=True)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth dialog."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()
