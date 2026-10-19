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

import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .config import ENTITY_SCHEMA
from .const import DOMAIN
from .entity import EntityController
from .entity_services import async_setup_entity_services
from .machine import build_machine

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = cv.schema_with_slug_keys(ENTITY_SCHEMA)


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

    devices = []
    # PLATFORM_SCHEMA makes HA hand us a list, one item per configuration block.
    for block in config[DOMAIN]:
        _LOGGER.info("Domain Configuration: %s", block)
        for key, ec_config in block.items():
            ec_config = {**(ec_config or {}), "name": key}
            devices.append(EntityController(hass, ec_config, machine))

    await component.async_add_entities(devices)

    _LOGGER.info("The %s component is ready!", DOMAIN)

    return True
