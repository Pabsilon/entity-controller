"""Smoke tests for the Entity Controller integration."""

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

# Importing the integration here makes sure our `custom_components` package is the
# one Python caches, instead of the plugin's testing_config package.
from custom_components.entity_controller.const import DOMAIN

ENTITY_ID = f"{DOMAIN}.room"
SENSOR = "binary_sensor.motion"
LIGHT = "light.room"
DELAY = 5
# Matches STARTUP_DELAY in the integration; EC stays `pending` until it elapses.
STARTUP_DELAY = 70


async def _advance(hass: HomeAssistant, freezer, seconds: int) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.fixture
async def calls(hass: HomeAssistant, freezer):
    """Set up an EC controlling a light from a motion sensor, past its startup delay."""
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    turn_on = async_mock_service(hass, "light", "turn_on")
    turn_off = async_mock_service(hass, "light", "turn_off")

    assert await async_setup_component(
        hass,
        DOMAIN,
        {DOMAIN: {"room": {"sensor": SENSOR, "entity": LIGHT, "delay": DELAY}}},
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "pending"

    await _advance(hass, freezer, STARTUP_DELAY + 1)
    assert hass.states.get(ENTITY_ID).state == "idle"
    # Entering idle turns the controlled entities off.
    assert len(turn_off) == 1
    turn_off.clear()

    return turn_on, turn_off


async def test_services_registered(hass: HomeAssistant, calls) -> None:
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
    hass: HomeAssistant, freezer, calls
) -> None:
    turn_on, turn_off = calls

    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "active_timer"
    assert len(turn_on) == 1
    assert turn_on[0].data["entity_id"] == LIGHT

    hass.states.async_set(SENSOR, "off")
    await _advance(hass, freezer, DELAY + 1)
    assert hass.states.get(ENTITY_ID).state == "idle"
    assert len(turn_off) == 1
    assert turn_off[0].data["entity_id"] == LIGHT


async def test_motion_resets_timer(hass: HomeAssistant, freezer, calls) -> None:
    _, turn_off = calls

    hass.states.async_set(SENSOR, "on")
    await _advance(hass, freezer, DELAY - 2)
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(SENSOR, "on")
    await _advance(hass, freezer, DELAY - 2)
    assert hass.states.get(ENTITY_ID).state == "active_timer"
    assert len(turn_off) == 0

    await _advance(hass, freezer, 3)
    assert hass.states.get(ENTITY_ID).state == "idle"
    assert len(turn_off) == 1


async def test_light_turned_on_elsewhere_blocks_motion(
    hass: HomeAssistant, freezer, calls
) -> None:
    """A light turned on by something else overrides EC until it goes off again."""
    turn_on, _ = calls

    hass.states.async_set(LIGHT, "on")
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "blocked"
    assert len(turn_on) == 0

    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "idle"

    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "active_timer"
    assert len(turn_on) == 1

    hass.states.async_set(SENSOR, "off")
    await _advance(hass, freezer, DELAY + 1)
    assert hass.states.get(ENTITY_ID).state == "idle"


async def test_clear_block_service(hass: HomeAssistant, freezer, calls) -> None:
    turn_on, _ = calls

    hass.states.async_set(LIGHT, "on")
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "blocked"

    await hass.services.async_call(
        DOMAIN, "clear_block", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "active_timer"
    assert len(turn_on) == 1

    hass.states.async_set(SENSOR, "off")
    await _advance(hass, freezer, DELAY + 1)
    assert hass.states.get(ENTITY_ID).state == "idle"
