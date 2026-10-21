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
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey
from transitions.extensions import HierarchicalMachine

from .config import validate_entity_controllers
from .const import DOMAIN
from .entity import EntityController
from .entity_services import async_setup_entity_services
from .machine import build_machine

_LOGGER = logging.getLogger(__name__)

ISSUE_DEPRECATED_YAML = "deprecated_yaml"
ISSUE_YAML_CONFLICT = "yaml_conflict"

CONFIG_SCHEMA = vol.Schema({DOMAIN: validate_entity_controllers}, extra=vol.ALLOW_EXTRA)


@dataclass
class EntityControllerData:
    """Shared by every EC, whether it comes from YAML or a config entry."""

    component: EntityComponent[EntityController]
    machine: HierarchicalMachine


DATA: HassKey[EntityControllerData] = HassKey(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component, and import each Entity Controller from YAML."""
    component = EntityComponent[EntityController](_LOGGER, DOMAIN, hass)
    machine = build_machine()
    hass.data[DATA] = EntityControllerData(component, machine)

    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info(
        "If you have ANY issues with EntityController (v%s), please enable DEBUG "
        "logging under the logger component and kindly report the issue on Github. "
        "https://github.com/Pabsilon/entity-controller/issues",
        integration.version,
    )

    async_setup_entity_services(component)

    if DOMAIN in config:
        _LOGGER.info("Domain Configuration: %s", config[DOMAIN])
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_DEPRECATED_YAML,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_DEPRECATED_YAML,
        )
        for key, ec_config in config[DOMAIN].items():
            hass.async_create_task(_async_import(hass, key, ec_config))
    else:
        issues = ir.async_get(hass).issues
        for domain, issue_id in list(issues):
            if domain == DOMAIN and (
                issue_id == ISSUE_DEPRECATED_YAML
                or issue_id.startswith(f"{ISSUE_YAML_CONFLICT}_")
            ):
                ir.async_delete_issue(hass, DOMAIN, issue_id)

    _LOGGER.info("The %s component is ready!", DOMAIN)

    return True


async def _async_import(hass: HomeAssistant, key: str, config: dict[str, Any]) -> None:
    """Import an EC from YAML, or raise an issue if a UI EC already has its name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data={**config, CONF_NAME: key}
    )
    issue_id = f"{ISSUE_YAML_CONFLICT}_{key}"
    if (
        result["type"] is not FlowResultType.ABORT
        or result["reason"] != ISSUE_YAML_CONFLICT
    ):
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, key)
    title = entry.title if entry else key
    _LOGGER.error(
        "Not importing '%s' from YAML: the Entity Controller '%s' already uses "
        "that name. Rename the YAML key to import it",
        key,
        title,
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_YAML_CONFLICT,
        translation_placeholders={"key": key, "title": title},
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Entity Controller from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return await hass.data[DATA].component.async_setup_entry(entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.data[DATA].component.async_unload_entry(entry)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options by reloading the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
