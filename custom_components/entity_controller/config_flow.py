"""Config flow: set up Entity Controllers from the UI.

Each EC is a config entry. Its options hold the EC's config in the same shape as
YAML, so `ENTITY_SCHEMA` validates both and the model reads both the same way.
"""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .config import ENTITY_SCHEMA
from .const import (
    CONF_CONTROL_ENTITIES,
    CONF_DELAY,
    CONF_SENSORS,
    DEFAULT_DELAY,
    DOMAIN,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Required(CONF_SENSORS): selector.EntitySelector(
            selector.EntitySelectorConfig(multiple=True)
        ),
        vol.Required(CONF_CONTROL_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(multiple=True)
        ),
        vol.Required(CONF_DELAY, default=DEFAULT_DELAY): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                step=1,
                unit_of_measurement="s",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
)


class EntityControllerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create an Entity Controller."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input.pop(CONF_NAME).strip()
            slug = slugify(name)
            if not slug or slug == "unknown":
                errors[CONF_NAME] = "invalid_name"
            else:
                await self.async_set_unique_id(slug)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name, data={}, options=ENTITY_SCHEMA(user_input)
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )
