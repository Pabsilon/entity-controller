"""The Entity Controller entity, which exposes a model's state to Home Assistant."""

import logging
from typing import Any

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from transitions.extensions import HierarchicalMachine

from . import entity_services
from .const import CONF_DELAY, PERSISTED_STATE_ATTRIBUTES
from .model import Model

_LOGGER = logging.getLogger(__name__)

ICONS = {
    "idle": "mdi:circle-outline",
    "active": "mdi:check-circle",
    "active_timer": "mdi:timer-outline",
    "constrained": "mdi:cancel",
    "overridden": "mdi:timer-off-outline",
    "blocked": "mdi:close-circle",
}


class EntityController(Entity):
    """Pushes the model's state and attributes to HA whenever they change."""

    _attr_should_poll = False

    async_activate = entity_services.async_entity_service_activate
    async_clear_block = entity_services.async_entity_service_clear_block
    async_enable_block = entity_services.async_entity_service_enable_block
    async_enable_stay_mode = entity_services.async_entity_service_enable_stay_mode
    async_disable_stay_mode = entity_services.async_entity_service_disable_stay_mode
    async_set_night_mode = entity_services.async_entity_service_set_night_mode

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        machine: HierarchicalMachine,
    ) -> None:
        self._attr_name = config.get("friendly_name", config.get(CONF_NAME))
        self._attributes: dict[str, Any] = {}
        self.model = Model(hass, config, machine, self)

    @property
    def state(self) -> str:
        """Return the state of the entity."""
        return self.model.state

    @property
    def icon(self) -> str:
        """Return the entity icon."""
        return ICONS.get(self.model.state, "mdi:eye")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the entity."""
        return self._attributes.copy()

    def reset_state(self) -> None:
        """Drop state-specific attributes when returning to idle state."""
        _LOGGER.debug("Resetting state")
        self._attributes = {
            k: v for k, v in self._attributes.items() if k in PERSISTED_STATE_ATTRIBUTES
        }
        self.do_update()

    @callback
    def do_update(self) -> None:
        """Write the current state to HA, once the entity has been added."""
        if self.hass is not None:
            self.async_write_ha_state()

    def set_attr(self, k: str, v: Any) -> None:
        if k == CONF_DELAY:
            v = f"{v}s"
        self._attributes[k] = v
