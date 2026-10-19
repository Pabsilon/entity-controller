"""Configuration schemas.

`ENTITY_SCHEMA` only checks that a controlled entity is configured: the dict below
is passed as `vol.Schema`'s `required` argument, not as part of the schema, so its
validators and defaults are never applied and the model receives the raw YAML.
"""

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import (
    CONF_BEHAVIOURS,
    CONF_BLOCK_TIMEOUT,
    CONF_CONTROL_ENTITIES,
    CONF_CONTROL_ENTITY,
    CONF_DELAY,
    CONF_DISABLE_BLOCK,
    CONF_END_TIME,
    CONF_IGNORED_EVENT_SOURCES,
    CONF_NIGHT_MODE,
    CONF_SENSOR,
    CONF_SENSOR_RESETS_TIMER,
    CONF_SENSOR_TYPE,
    CONF_SENSOR_TYPE_DURATION,
    CONF_SENSORS,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA_OFF,
    CONF_START_TIME,
    CONF_STATE_ATTRIBUTES_IGNORE,
    CONF_STATE_ENTITIES,
    CONF_TRIGGER_ON_ACTIVATE,
    CONF_TRIGGER_ON_DEACTIVATE,
    DEFAULT_DELAY,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
)

MODE_SCHEMA = vol.Schema(
    {
        # Default must be None because we differentiate between set and unset
        vol.Optional(CONF_SERVICE_DATA, default=None): vol.Coerce(dict),
        vol.Optional(CONF_SERVICE_DATA_OFF, default=None): vol.Coerce(dict),
        vol.Required(CONF_START_TIME): cv.string,
        vol.Required(CONF_END_TIME): cv.string,
        vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): cv.positive_int,
    }
)

ENTITY_SCHEMA = vol.Schema(
    cv.has_at_least_one_key(
        CONF_CONTROL_ENTITIES, CONF_CONTROL_ENTITY, CONF_TRIGGER_ON_ACTIVATE
    ),
    {
        vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): cv.positive_int,
        vol.Optional(CONF_START_TIME): cv.string,
        vol.Optional(CONF_END_TIME): cv.string,
        vol.Optional(CONF_SENSOR_TYPE_DURATION, default=False): cv.boolean,
        vol.Optional(CONF_SENSOR_TYPE, default=SENSOR_TYPE_EVENT): vol.All(
            vol.Lower, vol.Any(SENSOR_TYPE_EVENT, SENSOR_TYPE_DURATION)
        ),
        vol.Optional(CONF_SENSOR_RESETS_TIMER, default=False): cv.boolean,
        vol.Optional(CONF_SENSOR, default=[]): cv.entity_ids,
        vol.Optional(CONF_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_CONTROL_ENTITIES, default=[]): cv.entity_ids,
        vol.Optional(CONF_CONTROL_ENTITY, default=[]): cv.entity_ids,
        vol.Optional(CONF_TRIGGER_ON_ACTIVATE, default=None): cv.entity_ids,
        vol.Optional(CONF_TRIGGER_ON_DEACTIVATE, default=None): cv.entity_ids,
        vol.Optional(CONF_STATE_ENTITIES, default=[]): cv.entity_ids,
        vol.Optional(CONF_BLOCK_TIMEOUT, default=None): cv.positive_int,
        vol.Optional(CONF_DISABLE_BLOCK, default=False): cv.boolean,
        vol.Optional(CONF_NIGHT_MODE, default=None): MODE_SCHEMA,
        vol.Optional(CONF_STATE_ATTRIBUTES_IGNORE, default=[]): cv.ensure_list,
        vol.Optional(CONF_IGNORED_EVENT_SOURCES, default=[]): cv.ensure_list,
        # Default must be None because we differentiate between set and unset
        vol.Optional(CONF_SERVICE_DATA, default=None): vol.Coerce(dict),
        vol.Optional(CONF_SERVICE_DATA_OFF, default=None): vol.Coerce(dict),
        vol.Optional(CONF_BEHAVIOURS, default=None): vol.Coerce(dict),
    },
)
