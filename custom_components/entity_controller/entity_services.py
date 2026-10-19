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

Entity Service Definitions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.core import callback
from homeassistant.helpers.entity_component import EntityComponent

from .const import (
    CONF_END_TIME,
    CONF_START_TIME,
    SERVICE_ACTIVATE,
    SERVICE_CLEAR_BLOCK,
    SERVICE_DISABLE_STAY_MODE,
    SERVICE_ENABLE_BLOCK,
    SERVICE_ENABLE_STAY_MODE,
    SERVICE_SET_NIGHT_MODE,
)

if TYPE_CHECKING:
    from .entity import EntityController

TIME_STR_FORMAT = "%H:%M:%S"


def async_setup_entity_services(component: EntityComponent) -> None:
    """Setup Entity services."""

    component.logger.debug("Setting up entity services")
    component.async_register_entity_service(SERVICE_ACTIVATE, {}, "async_activate")
    component.async_register_entity_service(
        SERVICE_CLEAR_BLOCK, {}, "async_clear_block"
    )
    component.async_register_entity_service(
        SERVICE_ENABLE_BLOCK, {}, "async_enable_block"
    )
    component.async_register_entity_service(
        SERVICE_ENABLE_STAY_MODE, {}, "async_enable_stay_mode"
    )
    component.async_register_entity_service(
        SERVICE_DISABLE_STAY_MODE, {}, "async_disable_stay_mode"
    )
    component.async_register_entity_service(
        SERVICE_SET_NIGHT_MODE,
        {
            vol.Optional(CONF_START_TIME): cv.string,
            vol.Optional(CONF_END_TIME): cv.string,
        },
        "async_set_night_mode",
    )


@callback
def async_entity_service_activate(self: EntityController) -> None:
    """Activates the entity controller"""

    self.model.log.debug("Activating the Entity Controller")
    self.model.activate()


@callback
def async_entity_service_clear_block(self: EntityController) -> None:
    """Clear the block property, if set"""

    if self.model.state != "blocked":
        return

    self.model.log.debug("Clearing Blocked state")
    self.model.block_timer_expires()


@callback
def async_entity_service_enable_block(self: EntityController) -> None:
    """Enable the block property, if timer is active"""

    if self.model.state != "active_timer":
        return

    self.model.log.debug("Enabling Blocked state")
    self.model.block_enable()


@callback
def async_entity_service_enable_stay_mode(self: EntityController) -> None:
    self.model.log.debug(
        "Enable stay mode - Control entities will remain on until manually turned off"
    )
    self.model.stay = True


@callback
def async_entity_service_disable_stay_mode(self: EntityController) -> None:
    self.model.log.debug("Disable stay mode - Control entities will be managed by EC")
    self.model.stay = False


@callback
def async_entity_service_set_night_mode(
    self: EntityController, start_time: str | None = None, end_time: str | None = None
) -> None:
    """Changes the night mode start and/or end times"""

    if self.model.night_mode is None:
        return

    if start_time == "now":
        start_time = dt_util.as_local(dt_util.utcnow()).strftime(TIME_STR_FORMAT)
    elif start_time == "constraint":
        start_time = self.model.start_time_setting

    if end_time == "now":
        end_time = dt_util.as_local(dt_util.utcnow()).strftime(TIME_STR_FORMAT)
    elif end_time == "constraint":
        end_time = self.model.end_time_setting

    if start_time is None and end_time is None:
        start_time = end_time = "00:00:00"

    if start_time is not None:
        self.model.log.debug("Setting Night Mode Start to: %s", start_time)
        self.model.night_mode[CONF_START_TIME] = start_time

    if end_time is not None:
        self.model.log.debug("Setting Night Mode End to: %s", end_time)
        self.model.night_mode[CONF_END_TIME] = end_time

    self.model.prepare_service_data()
