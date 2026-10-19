"""
This file is part of Entity Controller.

Entity Controller is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Entity Controller is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Entity Controller.  If not, see <https://www.gnu.org/licenses/>.

Entity controller component for Home Assistant.
Maintainer:       Daniel Mason
Project Page:     https://danielbkr.net/projects/entity-controller/
Documentation:    https://github.com/Pabsilon/entity-controller
"""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .config import validate_entity_controllers
from .const import DOMAIN
from .entity import EntityController
from .entity_services import async_setup_entity_services
from .machine import build_machine

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: validate_entity_controllers}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up an Entity Controller for each configured key."""
    component = EntityComponent[EntityController](_LOGGER, DOMAIN, hass)

    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info(
        "If you have ANY issues with EntityController (v%s), please enable DEBUG "
        "logging under the logger component and kindly report the issue on Github. "
        "https://github.com/Pabsilon/entity-controller/issues",
        integration.version,
    )

    async_setup_entity_services(component)

    machine = build_machine()

    _LOGGER.info("Domain Configuration: %s", config[DOMAIN])
    devices = [
        EntityController(hass, {**ec_config, "name": key}, machine)
        for key, ec_config in config[DOMAIN].items()
    ]

    await component.async_add_entities(devices)

    _LOGGER.info("The %s component is ready!", DOMAIN)

    return True
