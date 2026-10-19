"""Configuration schemas.

The schemas set no defaults: the model's `config.get(...)` fallbacks are the only
source of defaults, because some of them depend on other keys (a night mode without
a `delay` uses the main `delay`, and `sensor_type_duration` applies only when
`sensor_type` is unset). Unknown keys are kept and logged as warnings, so a typo is
reported without breaking setup.
"""

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from . import time_utils
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
    CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_TRANSITION_BEHAVIOUR_OFF,
    CONF_TRANSITION_BEHAVIOUR_ON,
    CONF_TRIGGER_ON_ACTIVATE,
    CONF_TRIGGER_ON_DEACTIVATE,
    DEFAULT_TRANSITION_BEHAVIOURS,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
)

_LOGGER = logging.getLogger(__name__)

STATE_LIST_KEYS = tuple(
    f"{kind}_states_{on_off}"
    for kind in ("control", "sensor", "override", "state")
    for on_off in ("on", "off")
) + ("state_strings_on", "state_strings_off")


def time_string(value: Any) -> str:
    """Validate a time string such as `20:00:00` or `sunset - 00:30:00`."""
    value = cv.string(value)
    if not time_utils.is_time_string(value):
        raise vol.Invalid(
            f"invalid time '{value}', expected HH:MM:SS, sunrise/sunset with an "
            "optional offset (sunset - 00:30:00), or YYYY-MM-DD HH:MM:SS"
        )
    return value


string_list = vol.All(cv.ensure_list, [cv.string])

MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_START_TIME): time_string,
        vol.Required(CONF_END_TIME): time_string,
        vol.Optional(CONF_DELAY): cv.positive_int,
        vol.Optional(CONF_SERVICE_DATA): dict,
        vol.Optional(CONF_SERVICE_DATA_OFF): dict,
    },
    extra=vol.ALLOW_EXTRA,
)

BEHAVIOURS_SCHEMA = vol.Schema(
    {
        vol.Optional(key): vol.All(
            vol.Lower,
            vol.In(
                (
                    CONF_TRANSITION_BEHAVIOUR_ON,
                    CONF_TRANSITION_BEHAVIOUR_OFF,
                    CONF_TRANSITION_BEHAVIOUR_IGNORE,
                )
            ),
        )
        for key in DEFAULT_TRANSITION_BEHAVIOURS
    },
    extra=vol.ALLOW_EXTRA,
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("friendly_name"): cv.string,
        vol.Optional(CONF_SENSOR): cv.entity_ids,
        vol.Optional(CONF_SENSORS): cv.entity_ids,
        vol.Optional(CONF_CONTROL_ENTITY): cv.entity_ids,
        vol.Optional(CONF_CONTROL_ENTITIES): cv.entity_ids,
        vol.Optional(CONF_TRIGGER_ON_ACTIVATE): cv.entity_ids,
        vol.Optional(CONF_TRIGGER_ON_DEACTIVATE): cv.entity_ids,
        vol.Optional(CONF_STATE_ENTITIES): cv.entity_ids,
        vol.Optional("override"): cv.entity_ids,
        vol.Optional("overrides"): cv.entity_ids,
        vol.Optional(CONF_DELAY): cv.positive_int,
        vol.Optional(CONF_SENSOR_TYPE): vol.All(
            vol.Lower, vol.In((SENSOR_TYPE_EVENT, SENSOR_TYPE_DURATION))
        ),
        vol.Optional(CONF_SENSOR_TYPE_DURATION): cv.boolean,
        vol.Optional(CONF_SENSOR_RESETS_TIMER): cv.boolean,
        vol.Optional(CONF_BLOCK_TIMEOUT): cv.positive_int,
        vol.Optional(CONF_DISABLE_BLOCK): cv.boolean,
        vol.Optional("stay_mode"): cv.boolean,
        vol.Optional("backoff"): cv.boolean,
        vol.Optional("backoff_factor"): vol.Any(cv.positive_int, cv.positive_float),
        vol.Optional("backoff_max"): cv.positive_int,
        vol.Optional(CONF_START_TIME): time_string,
        vol.Optional(CONF_END_TIME): time_string,
        vol.Optional(CONF_NIGHT_MODE): MODE_SCHEMA,
        vol.Optional(CONF_SERVICE_DATA): dict,
        vol.Optional(CONF_SERVICE_DATA_OFF): dict,
        vol.Optional(CONF_BEHAVIOURS): BEHAVIOURS_SCHEMA,
        vol.Optional(CONF_STATE_ATTRIBUTES_IGNORE): string_list,
        vol.Optional(CONF_IGNORED_EVENT_SOURCES): string_list,
        **{vol.Optional(key): string_list for key in STATE_LIST_KEYS},
    },
    extra=vol.ALLOW_EXTRA,
)

ENTITY_SCHEMA = vol.All(
    cv.has_at_least_one_key(
        CONF_CONTROL_ENTITIES, CONF_CONTROL_ENTITY, CONF_TRIGGER_ON_ACTIVATE
    ),
    OPTIONS_SCHEMA,
)


def _unknown_keys(schema: vol.Schema, config: dict[str, Any]) -> list[str]:
    known = {str(key) for key in schema.schema}
    return [key for key in config if key not in known]


def _warn_unknown_keys(name: str, config: dict[str, Any]) -> None:
    """Log a warning for each key of an EC's config that no schema knows."""
    unknown = _unknown_keys(OPTIONS_SCHEMA, config)
    for parent, schema in (
        (CONF_NIGHT_MODE, MODE_SCHEMA),
        (CONF_BEHAVIOURS, BEHAVIOURS_SCHEMA),
    ):
        if parent in config:
            unknown += [
                f"{parent}.{key}" for key in _unknown_keys(schema, config[parent])
            ]
    for key in unknown:
        _LOGGER.warning("%s: unknown option '%s', ignoring it", name, key)


def validate_entity_controllers(value: Any) -> dict[str, dict[str, Any]]:
    """Validate the `entity_controller:` section, a mapping of EC names to configs."""
    ecs = cv.schema_with_slug_keys(ENTITY_SCHEMA)(value)
    for name, config in ecs.items():
        _warn_unknown_keys(name, config)
    return ecs
