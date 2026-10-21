"""Config flow: set up Entity Controllers from the UI.

Each EC is a config entry. Its options hold the EC's config in the same shape as
YAML, so `ENTITY_SCHEMA` validates both and the model reads both the same way.

Both the create and the options form show every option, in sections. Options left
empty, or set to their default, are not saved, so the model's own fallbacks stay the
only source of defaults (a night mode without a delay uses the main delay, for
example).
"""

from typing import Any, NamedTuple

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .config import ENTITY_SCHEMA, STATE_LIST_KEYS
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
    DEFAULT_DELAY,
    DEFAULT_TRANSITION_BEHAVIOURS,
    DOMAIN,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
)

CONF_OVERRIDE = "override"
CONF_OVERRIDES = "overrides"

# Keys with more than one spelling, saved under the first one
ALIASES = {
    CONF_SENSORS: CONF_SENSOR,
    CONF_CONTROL_ENTITIES: CONF_CONTROL_ENTITY,
    CONF_OVERRIDES: CONF_OVERRIDE,
}

# Values the model uses when an option is not set, so they are not saved
DEFAULTS = {
    CONF_SENSOR_TYPE: SENSOR_TYPE_EVENT,
    CONF_SENSOR_RESETS_TIMER: False,
    "stay_mode": False,
    CONF_DISABLE_BLOCK: False,
    "backoff": False,
}

ENTITIES = selector.EntitySelector(selector.EntitySelectorConfig(multiple=True))
SECONDS = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX
    )
)
TIME = selector.TextSelector()
BOOLEAN = selector.BooleanSelector()
OBJECT = selector.ObjectSelector()
STRINGS = selector.TextSelector(selector.TextSelectorConfig(multiple=True))
BEHAVIOUR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            CONF_TRANSITION_BEHAVIOUR_ON,
            CONF_TRANSITION_BEHAVIOUR_OFF,
            CONF_TRANSITION_BEHAVIOUR_IGNORE,
        ],
        translation_key="behaviour",
    )
)


class Section(NamedTuple):
    """A section of the options form.

    `parent` is where its fields live in the options: `None` for the top level,
    otherwise the name of a nested dict. `fields` is keyed by the option's name;
    in the form each key gets `prefix`, so no two fields share a name. API clients
    such as MCP servers flatten the sections, and would mix them up otherwise.
    """

    parent: str | None
    prefix: str
    fields: dict[str, selector.Selector]


SECTIONS: dict[str, Section] = {
    "entity_settings": Section(
        None,
        "",
        {
            CONF_SENSORS: ENTITIES,
            CONF_CONTROL_ENTITIES: ENTITIES,
            CONF_TRIGGER_ON_ACTIVATE: ENTITIES,
            CONF_TRIGGER_ON_DEACTIVATE: ENTITIES,
            CONF_STATE_ENTITIES: ENTITIES,
            CONF_OVERRIDES: ENTITIES,
        },
    ),
    "timing": Section(
        None,
        "",
        {
            CONF_DELAY: SECONDS,
            CONF_SENSOR_TYPE: selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SENSOR_TYPE_EVENT, SENSOR_TYPE_DURATION],
                    translation_key="sensor_type",
                )
            ),
            CONF_SENSOR_RESETS_TIMER: BOOLEAN,
            "stay_mode": BOOLEAN,
            CONF_START_TIME: TIME,
            CONF_END_TIME: TIME,
        },
    ),
    "night_mode": Section(
        CONF_NIGHT_MODE,
        "night_",
        {
            CONF_START_TIME: TIME,
            CONF_END_TIME: TIME,
            CONF_DELAY: SECONDS,
            CONF_SERVICE_DATA: OBJECT,
            CONF_SERVICE_DATA_OFF: OBJECT,
        },
    ),
    "blocking": Section(
        None,
        "",
        {
            CONF_BLOCK_TIMEOUT: SECONDS,
            CONF_DISABLE_BLOCK: BOOLEAN,
            "backoff": BOOLEAN,
            "backoff_factor": selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, step=0.1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            "backoff_max": SECONDS,
        },
    ),
    "service_data_settings": Section(
        None,
        "",
        {CONF_SERVICE_DATA: OBJECT, CONF_SERVICE_DATA_OFF: OBJECT},
    ),
    "behaviours": Section(
        CONF_BEHAVIOURS,
        "",
        dict.fromkeys(DEFAULT_TRANSITION_BEHAVIOURS, BEHAVIOUR),
    ),
    "advanced": Section(
        None,
        "",
        {
            **dict.fromkeys(STATE_LIST_KEYS, STRINGS),
            CONF_STATE_ATTRIBUTES_IGNORE: STRINGS,
            CONF_IGNORED_EVENT_SOURCES: STRINGS,
        },
    ),
}

EXPANDED_SECTIONS = ("entity_settings", "timing")

OPTIONS_SCHEMA = vol.Schema(
    {
        # Optional: HA's UI sends every section, but API clients such as MCP
        # servers only send the ones that have values.
        vol.Optional(name): section(
            vol.Schema(
                {
                    vol.Optional(f"{sec.prefix}{key}"): field
                    for key, field in sec.fields.items()
                }
            ),
            {"collapsed": name not in EXPANDED_SECTIONS},
        )
        for name, sec in SECTIONS.items()
    }
)


# The create form: a name, then the same sections as the options form
USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_NAME): selector.TextSelector(), **OPTIONS_SCHEMA.schema}
)


def normalize(options: dict[str, Any]) -> dict[str, Any]:
    """Merge the legacy spellings of keys into the ones the form uses."""
    options = dict(options)
    for key, alias in ALIASES.items():
        merged: list[str] = []
        for value in (options.pop(alias, None), options.pop(key, None)):
            for entity_id in value or []:
                if entity_id not in merged:
                    merged.append(entity_id)
        if merged:
            options[key] = merged
    if options.pop(CONF_SENSOR_TYPE_DURATION, False):
        options.setdefault(CONF_SENSOR_TYPE, SENSOR_TYPE_DURATION)
    return options


def options_to_form(options: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Split the options into the form's sections, showing defaults where useful."""
    options = normalize(options)
    form: dict[str, dict[str, Any]] = {}
    for name, sec in SECTIONS.items():
        source = options if sec.parent is None else options.get(sec.parent, {})
        form[name] = {
            f"{sec.prefix}{key}": source[key] for key in sec.fields if key in source
        }
    form["timing"].setdefault(CONF_SENSOR_TYPE, SENSOR_TYPE_EVENT)
    form["behaviours"] = {**DEFAULT_TRANSITION_BEHAVIOURS, **form["behaviours"]}
    return form


def _is_set(key: str, value: Any, defaults: dict[str, Any]) -> bool:
    return value not in (None, "", [], {}) and (
        key not in defaults or value != defaults[key]
    )


def form_to_options(user_input: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Merge the form's sections into options, leaving out empty and default values."""
    options: dict[str, Any] = {}
    for name, sec in SECTIONS.items():
        defaults = {
            **DEFAULTS,
            **(DEFAULT_TRANSITION_BEHAVIOURS if sec.parent == CONF_BEHAVIOURS else {}),
        }
        section_input = user_input.get(name, {})
        values = {
            key: value
            for key in sec.fields
            if _is_set(key, value := section_input.get(f"{sec.prefix}{key}"), defaults)
        }
        if sec.parent is None:
            options.update(values)
        elif values:
            options[sec.parent] = values
    return options


def validate_form(
    user_input: dict[str, Any], errors: dict[str, str], placeholders: dict[str, str]
) -> dict[str, Any] | None:
    """Turn the form's sections into validated options, or add an error."""
    try:
        return ENTITY_SCHEMA(form_to_options(user_input))
    except vol.Invalid as err:
        errors["base"] = "invalid_options"
        placeholders["error"] = str(err)
        return None


class EntityControllerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create an Entity Controller."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EntityControllerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            slug = slugify(name)
            if not slug or slug == "unknown":
                errors[CONF_NAME] = "invalid_name"
            options = validate_form(user_input, errors, placeholders)
            if options is not None and not errors:
                await self.async_set_unique_id(slug)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=name, data={}, options=options)

        suggested = (
            user_input
            if user_input is not None
            else options_to_form({CONF_DELAY: DEFAULT_DELAY})
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )


class EntityControllerOptionsFlow(OptionsFlow):
    """Change every option of an Entity Controller.

    Saving reloads the entry (see the update listener in `__init__.py`), so the
    changes apply without restarting Home Assistant.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            options = validate_form(user_input, errors, placeholders)
            if options is not None:
                return self.async_create_entry(data=options)

        suggested = (
            user_input
            if user_input is not None
            else options_to_form(dict(self.config_entry.options))
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )
