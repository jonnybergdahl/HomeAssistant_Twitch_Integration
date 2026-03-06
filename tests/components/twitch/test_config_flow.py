"""Test config flow for Twitch."""

from unittest.mock import AsyncMock

import pytest
from twitchAPI.object.api import TwitchUser

from homeassistant.components.twitch.const import (
    CONF_ALL_CHANNELS,
    CONF_CHANNELS,
    DOMAIN,
    OAUTH2_AUTHORIZE,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow

from . import get_generator, setup_integration
from .conftest import CLIENT_ID, TITLE

from tests.common import MockConfigEntry
from tests.typing import ClientSessionGenerator


async def _do_get_token(
    hass: HomeAssistant,
    result: FlowResult,
    hass_client_no_auth: ClientSessionGenerator,
    scopes: list[str],
) -> None:
    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {
            "flow_id": result["flow_id"],
            "redirect_uri": "https://example.com/auth/external/callback",
        },
    )

    assert result["url"] == (
        f"{OAUTH2_AUTHORIZE}?response_type=code&client_id={CLIENT_ID}"
        "&redirect_uri=https://example.com/auth/external/callback"
        f"&state={state}&scope={'+'.join(scopes)}"
    )

    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"


@pytest.mark.usefixtures("current_request_with_host")
async def test_full_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    mock_setup_entry,
    twitch_mock: AsyncMock,
    scopes: list[str],
) -> None:
    """Check full flow adding all followed channels."""
    result = await hass.config_entries.flow.async_init(
        "twitch", context={"source": SOURCE_USER}
    )
    await _do_get_token(hass, result, hass_client_no_auth, scopes)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "channels"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"all_channels": True}
    )

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "channel123"
    assert "result" in result
    assert "token" in result["result"].data
    assert result["result"].data["token"]["access_token"] == "mock-access-token"
    assert result["result"].data["token"]["refresh_token"] == "mock-refresh-token"
    assert result["result"].unique_id == "123"
    assert result["options"] == {CONF_ALL_CHANNELS: True, CONF_CHANNELS: ["internetofthings", "homeassistant"]}


@pytest.mark.usefixtures("current_request_with_host")
async def test_full_flow_select_specific_channels(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    mock_setup_entry,
    twitch_mock: AsyncMock,
    scopes: list[str],
) -> None:
    """Check full flow selecting only specific channels."""
    result = await hass.config_entries.flow.async_init(
        "twitch", context={"source": SOURCE_USER}
    )
    await _do_get_token(hass, result, hass_client_no_auth, scopes)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["step_id"] == "channels"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"all_channels": False}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_channels"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_CHANNELS: ["internetofthings"]}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_ALL_CHANNELS: False, CONF_CHANNELS: ["internetofthings"]}


@pytest.mark.usefixtures("current_request_with_host")
async def test_select_channels_no_selection_error(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    mock_setup_entry,
    twitch_mock: AsyncMock,
    scopes: list[str],
) -> None:
    """Check that submitting no channels on the select step shows an error."""
    result = await hass.config_entries.flow.async_init(
        "twitch", context={"source": SOURCE_USER}
    )
    await _do_get_token(hass, result, hass_client_no_auth, scopes)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"all_channels": False}
    )
    assert result["step_id"] == "select_channels"

    # Submit with no channels selected
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_CHANNELS: []}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_channels"
    assert result["errors"] == {CONF_CHANNELS: "no_channels_selected"}

    # Correct the selection
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_CHANNELS: ["homeassistant"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_ALL_CHANNELS: False, CONF_CHANNELS: ["homeassistant"]}


@pytest.mark.usefixtures("current_request_with_host")
async def test_already_configured(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    config_entry: MockConfigEntry,
    mock_setup_entry,
    twitch_mock: AsyncMock,
    scopes: list[str],
) -> None:
    """Check flow aborts when account already configured."""
    await setup_integration(hass, config_entry)
    result = await hass.config_entries.flow.async_init(
        "twitch", context={"source": SOURCE_USER}
    )
    await _do_get_token(hass, result, hass_client_no_auth, scopes)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("current_request_with_host")
async def test_reauth(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    config_entry: MockConfigEntry,
    mock_setup_entry,
    twitch_mock: AsyncMock,
    scopes: list[str],
) -> None:
    """Check reauth flow."""
    await setup_integration(hass, config_entry)
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    await _do_get_token(hass, result, hass_client_no_auth, scopes)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


@pytest.mark.usefixtures("current_request_with_host")
async def test_reauth_from_import(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    mock_setup_entry,
    twitch_mock: AsyncMock,
    expires_at,
    scopes: list[str],
) -> None:
    """Check reauth flow."""
    config_entry = MockConfigEntry(
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
            "imported": True,
        },
        options={"channels": ["internetofthings"]},
    )
    await test_reauth(
        hass,
        hass_client_no_auth,
        config_entry,
        mock_setup_entry,
        twitch_mock,
        scopes,
    )
    entries = hass.config_entries.async_entries(DOMAIN)
    entry = entries[0]
    assert "imported" not in entry.data
    assert entry.options == {CONF_CHANNELS: ["internetofthings", "homeassistant"]}


@pytest.mark.usefixtures("current_request_with_host")
async def test_reauth_wrong_account(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    config_entry: MockConfigEntry,
    mock_setup_entry,
    twitch_mock: AsyncMock,
    scopes: list[str],
) -> None:
    """Check reauth flow."""
    await setup_integration(hass, config_entry)
    twitch_mock.return_value.get_users = lambda *args, **kwargs: get_generator(
        hass, "get_users_2.json", TwitchUser
    )
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    await _do_get_token(hass, result, hass_client_no_auth, scopes)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


@pytest.mark.usefixtures("current_request_with_host")
async def test_reconfigure_select_specific(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    twitch_mock: AsyncMock,
) -> None:
    """Check reconfigure flow allows switching to specific channels."""
    await setup_integration(hass, config_entry)

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    # Choose specific channels
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ALL_CHANNELS: False},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_channels"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CHANNELS: ["internetofthings", "homeassistant"]},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.options == {
        CONF_ALL_CHANNELS: False,
        CONF_CHANNELS: ["internetofthings", "homeassistant"],
    }


@pytest.mark.usefixtures("current_request_with_host")
async def test_reconfigure_all_channels(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    twitch_mock: AsyncMock,
) -> None:
    """Check reconfigure flow allows switching to all channels."""
    await setup_integration(hass, config_entry)

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ALL_CHANNELS: True},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # Existing channels are preserved; the coordinator discovers new ones at startup
    assert config_entry.options == {
        CONF_ALL_CHANNELS: True,
        CONF_CHANNELS: ["internetofthings"],
    }


@pytest.mark.usefixtures("current_request_with_host")
async def test_reconfigure_no_channels_error(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    twitch_mock: AsyncMock,
) -> None:
    """Check reconfigure flow shows an error when no channels are selected."""
    await setup_integration(hass, config_entry)

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    # Choose specific channels
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ALL_CHANNELS: False},
    )
    assert result["step_id"] == "reconfigure_channels"

    # Submit with no channels
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CHANNELS: []},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_channels"
    assert result["errors"] == {CONF_CHANNELS: "no_channels_selected"}

    # Correct the selection
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CHANNELS: ["homeassistant"]},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.options == {CONF_ALL_CHANNELS: False, CONF_CHANNELS: ["homeassistant"]}
