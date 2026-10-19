"""The `entity_controller` platform, which sets up the EC of a config entry.

`EntityComponent.async_setup_entry` loads the platform named after the entry's
domain, so for our own entries that is this module.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DATA
from .entity import EntityController


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Entity Controller of a config entry."""
    config = {
        **entry.options,
        CONF_NAME: entry.unique_id,
        "friendly_name": entry.title,
    }
    async_add_entities(
        [EntityController(hass, config, hass.data[DATA].machine, entry.entry_id)]
    )
