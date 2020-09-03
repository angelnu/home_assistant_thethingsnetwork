"""Support for The Things Network's Data storage integration."""
from .TTN_client import TTN_client


async def async_setup_entry(hass, entry, async_add_entities):
    """Add entities for TTN."""
    client = TTN_client.getInstance(entry)
    client.add_sensors(async_add_entities)



async def async_unload_entry(hass, entry, async_remove_entity) -> None:
    print("DELETING")
    """Handle removal of an entry."""
    client = TTN_client.getInstance(entry)
    client.remove_sensors(async_remove_entity)