"""The Entity Controller entity, which exposes a model's state to Home Assistant."""

import logging

from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import entity, event

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


class EntityController(entity.Entity):
    async_activate = entity_services.async_entity_service_activate
    async_clear_block = entity_services.async_entity_service_clear_block
    async_enable_block = entity_services.async_entity_service_enable_block
    async_enable_stay_mode = entity_services.async_entity_service_enable_stay_mode
    async_disable_stay_mode = entity_services.async_entity_service_disable_stay_mode
    async_set_night_mode = entity_services.async_entity_service_set_night_mode

    def __init__(self, hass, config, machine):
        self.attributes = {}
        self.may_update = False
        self.model = None
        self.friendly_name = config.get(CONF_NAME, "Motion Light")
        if "friendly_name" in config:
            self.friendly_name = config.get("friendly_name")
        try:
            self.model = Model(hass, config, machine, self)
        except AttributeError:
            _LOGGER.exception(
                "Configuration error! Please ensure you use plural keys for lists. "
                "e.g. sensors, entities."
            )
        event.async_call_later(hass, 1, self.do_update)

    @property
    def state(self):
        """Return the state of the entity."""
        return self.model.state

    @property
    def name(self):
        """Return the name of the entity."""
        return self.friendly_name

    @property
    def icon(self):
        """Return the entity icon."""
        return ICONS.get(self.model.state, "mdi:eye")

    @property
    def state_attributes(self):
        """Return the state attributes of the entity."""
        return self.attributes.copy()

    def reset_state(self):
        """Drop state-specific attributes when returning to idle state."""
        _LOGGER.debug("Resetting state")
        self.attributes = {
            k: v for k, v in self.attributes.items() if k in PERSISTED_STATE_ATTRIBUTES
        }
        self.do_update()

    @callback
    def do_update(self, wait=False, **kwargs):
        """Schedules an entity state update with HASS"""
        if self.may_update:
            self.async_schedule_update_ha_state(True)

    def set_attr(self, k, v):
        if k == CONF_DELAY:
            v = f"{v}s"
        self.attributes[k] = v

    # HA Callbacks
    async def async_added_to_hass(self):
        """Register update dispatcher."""
        self.may_update = True

    @property
    def should_poll(self) -> bool:
        """EntityController will push its state to HA"""
        return False
