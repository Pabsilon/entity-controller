"""Smoke tests for the Entity Controller integration."""

import pytest
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

# Importing the integration here makes sure our `custom_components` package is the
# one Python caches, instead of the plugin's testing_config package.
from custom_components.entity_controller.const import DOMAIN

from .conftest import (
    STARTUP_DELAY,
    ServiceCalls,
    SetupEC,
    advance,
    ec_state,
    get_entity,
    setup_at_boot,
)

ENTITY_ID = f"{DOMAIN}.room"
SENSOR = "binary_sensor.motion"
LIGHT = "light.room"
DELAY = 5
CONFIG = {"sensor": SENSOR, "entity": LIGHT, "delay": DELAY}


async def _setup(hass: HomeAssistant, setup_ec: SetupEC) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await setup_ec(CONFIG)
    assert ec_state(hass) == "idle"


async def test_pending_until_startup_delay(
    hass: HomeAssistant, freezer, calls: ServiceCalls
) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await setup_at_boot(hass, {"room": CONFIG})
    calls.register()
    assert ec_state(hass) == "pending"

    # Motion during the startup delay is ignored.
    hass.states.async_set(SENSOR, "on")
    await advance(hass, freezer, STARTUP_DELAY - 1)
    assert ec_state(hass) == "pending"
    assert calls.turned_on() == []

    await advance(hass, freezer, 2)
    assert ec_state(hass) == "idle"
    # Entering idle turns the controlled entities off.
    assert len(calls.turned_off(LIGHT)) == 1


async def test_services_registered(hass: HomeAssistant, setup_ec: SetupEC) -> None:
    await _setup(hass, setup_ec)
    for service in (
        "activate",
        "clear_block",
        "enable_block",
        "enable_stay_mode",
        "disable_stay_mode",
        "set_night_mode",
    ):
        assert hass.services.has_service(DOMAIN, service)


async def test_motion_turns_light_on_then_off(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)

    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"
    assert len(calls.turned_on(LIGHT)) == 1

    hass.states.async_set(SENSOR, "off")
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"
    assert len(calls.turned_off(LIGHT)) == 1


async def test_motion_resets_timer(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)

    hass.states.async_set(SENSOR, "on")
    await advance(hass, freezer, DELAY - 2)
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(SENSOR, "on")
    await advance(hass, freezer, DELAY - 2)
    assert ec_state(hass) == "active_timer"
    assert calls.turned_off() == []

    await advance(hass, freezer, 3)
    assert ec_state(hass) == "idle"
    assert len(calls.turned_off(LIGHT)) == 1


async def test_own_state_changes_are_ignored(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    """The light turning on because EC asked it to must not count as a manual change."""
    await _setup(hass, setup_ec)

    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == "on"
    assert ec_state(hass) == "active_timer"


async def test_attributes(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)
    attributes = hass.states.get(ENTITY_ID).attributes
    assert attributes["friendly_name"] == "room"
    assert attributes["sensor_type"] == "event"

    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    attributes = hass.states.get(ENTITY_ID).attributes
    assert attributes["last_triggered_by"] == SENSOR
    assert attributes["delay"] == f"{DELAY}s"
    assert "expires_at" in attributes

    # Returning to idle drops the per-activation attributes.
    await advance(hass, freezer, DELAY + 1)
    attributes = hass.states.get(ENTITY_ID).attributes
    assert attributes["last_triggered_by"] == SENSOR
    assert "expires_at" not in attributes


async def test_friendly_name_sets_entity_id(
    hass: HomeAssistant, setup_ec: SetupEC
) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await setup_ec(None, hall={**CONFIG, "friendly_name": "Upstairs Hall"})
    state = hass.states.get(f"{DOMAIN}.upstairs_hall")
    assert state.state == "idle"
    assert state.attributes["friendly_name"] == "Upstairs Hall"


async def test_multiple_controllers_are_independent(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    for entity_id in (SENSOR, LIGHT, "binary_sensor.motion2", "light.room2"):
        hass.states.async_set(entity_id, "off")
    await setup_ec(
        CONFIG,
        room2={"sensor": "binary_sensor.motion2", "entity": "light.room2", "delay": 20},
    )

    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"
    assert ec_state(hass, f"{DOMAIN}.room2") == "idle"
    assert calls.turned_on("light.room2") == []


async def test_state_history(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    """Only settled states are written; transitions don't leak intermediate ones."""
    await _setup(hass, setup_ec)
    history: list[str] = []

    @callback
    def record(event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old.state != new.state:
            history.append(new.state)

    async_track_state_change_event(hass, ENTITY_ID, record)

    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    hass.states.async_set(LIGHT, "on", {"brightness": 10})
    await hass.async_block_till_done()
    hass.states.async_set(LIGHT, "off")
    await hass.async_block_till_done()

    assert history == ["active_timer", "blocked", "idle"]


async def test_removing_the_entity_stops_its_timers(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"

    await get_entity(hass).async_remove()
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(SENSOR, "on")
    await advance(hass, freezer, DELAY + 1)
    assert hass.states.get(ENTITY_ID) is None
    assert calls.turned_off() == []


async def test_config_is_not_modified(hass: HomeAssistant, setup_ec: SetupEC) -> None:
    config = dict(CONFIG)
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await setup_ec(config)
    assert config == CONFIG


@pytest.mark.parametrize("removed", [SENSOR, LIGHT])
async def test_removed_watched_entity(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC, removed
) -> None:
    """A watched entity disappearing (e.g. deleted or renamed) is ignored."""
    await _setup(hass, setup_ec)
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()

    hass.states.async_remove(removed)
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"
