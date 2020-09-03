"""Support for The Things network."""
import logging
import asyncio

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

LOGGER = logging.getLogger(__name__)
print(__name__)

from .const import *
from .TTN_client import TTN_client



CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_APP_ID): cv.string,
                vol.Required(CONF_ACCESS_KEY): cv.string,
                vol.Required(CONF_VALUES, default={}): {
                    cv.string: {
                        CONF_VALUES_NAME: cv.string,
                        CONF_VALUES_UNIT: cv.string,
                    }
                },
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Initialize of The Things Network component."""

    # if DOMAIN in config:
    #     conf = config[DOMAIN]

    #     hass.async_create_task(
    #         hass.config_entries.flow.async_init(
    #             DOMAIN, context={"source": SOURCE_IMPORT}, data=conf
    #         )
    #     )

    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Establish connection with The Things Network."""
    
    LOGGER.debug(f"Set up {entry.data[CONF_APP_ID]}")

    client = TTN_client.createInstance(hass, entry)

    await client.connect()

    # conf = entry.data
    # # hass.data.setdefault(DOMAIN, {}).update({entry.unique_id: conf})
    # for component in COMPONENT_TYPES:
    #     hass.async_add_job(
    #         hass.config_entries.async_forward_entry_setup(entry, component)
    #     )
    return True

async def async_unload_entry(hass, entry) -> None:
    """Unload a config entry."""

    LOGGER.debug(f"Remove {entry.data[CONF_APP_ID]}")
    return await TTN_client.deleteInstance(hass, entry)

    # await asyncio.wait(
    #     [
    #         hass.config_entries.async_forward_entry_unload(entry, component)
    #         for component in COMPONENT_TYPES
    #     ]
    # )
    # hass.data[DOMAIN].pop(entry.unique_id)
    # if not hass.data[DOMAIN]:
    #     hass.data.pop(DOMAIN)
