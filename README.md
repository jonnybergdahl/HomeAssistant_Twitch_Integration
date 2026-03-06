# Twitch integration for Home Assistant (beta)

This is a beta version of the enhanced Twitch integration for Home Assistant, distributed via HACS for testing before merging into HA core.

> **Note:** This custom integration will override the built-in Twitch integration. Remove it from HACS when the changes are merged into Home Assistant core.

## Changes

Changes compared to the original Twitch integration.

 - New: Backend changes to use the Twitch EventSub push service for real-time updates.
 - New: Owner sensor is moved to it's own type, with fast EventSub updates for follower and subscriber updates
 - New: Dedicated binary sensors for followed Twitch channels stream status.
 - New: Channel selection in config flow
 - New: Adds the Calender platform
 - Change: GUI OAuth repair
 - Change: Faster integration load, attributes are now fetched after Home Assistant is started

Note: Due to Twitch EventSub limits, it is only used for followed channels if they are 12 or less. 
The integration automatically switches to one minute polling for followed channels if that limit is exceeded.

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add this repository URL: `https://github.com/jonnybergdahl/HomeAssistant_Twitch_Integration`
4. Select **Integration** as the category.
5. Click **Add**.
6. Search for "Twitch" in HACS and install it.
7. Restart Home Assistant.

### Manual installation

1. Copy the `custom_components/twitch` directory to your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

This integration uses the standard Twitch configuration flow with OAuth. See the [Home Assistant Twitch documentation](https://www.home-assistant.io/integrations/twitch) for setup instructions.
