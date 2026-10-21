"""Fixtures for Entity Controller tests."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.entity_controller.const import DOMAIN, STARTUP_DELAY
from custom_components.entity_controller.entity import EntityController

# Domains whose turn_on/turn_off services are faked. `homeassistant` is used for
# groups, `script` for trigger_on_activate/trigger_on_deactivate.
FAKE_DOMAINS = ("light", "switch", "script", "homeassistant")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


async def advance(hass: HomeAssistant, freezer, seconds: float) -> None:
    """Move HA's clock forward and run whatever timers became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def setup_at_boot(hass: HomeAssistant, ecs: dict[str, Any]) -> None:
    """Set up ECs from YAML the way HA does at boot, before it is running.

    The test instance is already running, and ECs set up while HA is running skip
    the startup delay.
    """
    hass.set_state(CoreState.not_running)
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: ecs})
    await hass.async_block_till_done()
    hass.set_state(CoreState.running)


def ec_state(hass: HomeAssistant, entity_id: str = f"{DOMAIN}.room") -> str:
    return hass.states.get(entity_id).state


def get_entity(
    hass: HomeAssistant, entity_id: str = f"{DOMAIN}.room"
) -> EntityController:
    return hass.data[DATA_INSTANCES][DOMAIN].get_entity(entity_id)


class ServiceCalls:
    """Records turn_on/turn_off calls and, like a real device, applies the new state.

    The state change carries the caller's context, so EC sees its own calls the
    same way it does in a real instance.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[ServiceCall] = []

    def register(self) -> None:
        for domain in FAKE_DOMAINS:
            for service in ("turn_on", "turn_off"):
                self.hass.services.async_register(domain, service, self._handle)

    async def _handle(self, call: ServiceCall) -> None:
        self.calls.append(call)
        entity_id = call.data.get("entity_id")
        if entity_id and call.domain != "script":
            new_state = "on" if call.service == "turn_on" else "off"
            self.hass.states.async_set(entity_id, new_state, context=call.context)

    def of(self, service: str, entity_id: str | None = None) -> list[ServiceCall]:
        return [
            c
            for c in self.calls
            if c.service == service
            and (entity_id is None or c.data.get("entity_id") == entity_id)
        ]

    def turned_on(self, entity_id: str | None = None) -> list[ServiceCall]:
        return self.of("turn_on", entity_id)

    def turned_off(self, entity_id: str | None = None) -> list[ServiceCall]:
        return self.of("turn_off", entity_id)

    def clear(self) -> None:
        self.calls.clear()


@pytest.fixture
def calls(hass: HomeAssistant) -> ServiceCalls:
    return ServiceCalls(hass)


SetupEC = Callable[..., Awaitable[None]]


@pytest.fixture
def setup_ec(hass: HomeAssistant, freezer, calls: ServiceCalls) -> SetupEC:
    """Set up one or more ECs and run them past the startup delay.

    Initial states of sensors and controlled entities should be set before calling.
    Service calls made during startup (entering idle turns everything off) are
    cleared, so tests only see what happens afterwards.
    """

    async def _setup(config: dict[str, Any] | None = None, **ecs: dict) -> None:
        if config is not None:
            ecs = {"room": config, **ecs}
        await setup_at_boot(hass, ecs)
        # Registered after setup so nothing set up alongside EC replaces them.
        calls.register()
        await advance(hass, freezer, STARTUP_DELAY + 1)
        calls.clear()

    return _setup
