"""Overrides, stay mode, duration sensors and backoff."""

import pytest
from homeassistant.core import HomeAssistant

from custom_components.entity_controller.const import DOMAIN

from .conftest import ServiceCalls, SetupEC, advance, ec_state

ENTITY_ID = f"{DOMAIN}.room"
SENSOR = "binary_sensor.motion"
LIGHT = "light.room"
OVERRIDE = "input_boolean.guests"
TV = "media_player.tv"
DELAY = 5


async def _setup(hass: HomeAssistant, setup_ec: SetupEC, **config) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await setup_ec({"sensor": SENSOR, "entity": LIGHT, "delay": DELAY, **config})


async def _motion(hass: HomeAssistant) -> None:
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    hass.states.async_set(SENSOR, "off")
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()


# Overrides


@pytest.mark.parametrize("key", ["override", "overrides"])
async def test_override(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC, key: str
) -> None:
    hass.states.async_set(OVERRIDE, "off")
    await _setup(hass, setup_ec, **{key: OVERRIDE})

    await _set(hass, OVERRIDE, "on")
    assert ec_state(hass) == "overridden"
    assert hass.states.get(ENTITY_ID).attributes["overridden_by"] == OVERRIDE

    await _motion(hass)
    assert ec_state(hass) == "overridden"
    assert calls.turned_on() == []

    await _set(hass, OVERRIDE, "off")
    assert ec_state(hass) == "idle"

    await _motion(hass)
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"


async def test_override_on_at_startup(
    hass: HomeAssistant, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    hass.states.async_set(OVERRIDE, "on")
    await _setup(hass, setup_ec, override=OVERRIDE)
    assert ec_state(hass) == "overridden"

    await _set(hass, OVERRIDE, "off")
    assert ec_state(hass) == "idle"


async def test_override_while_active(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    """The override leaves the light alone; when it ends, EC picks the light back up."""
    hass.states.async_set(OVERRIDE, "off")
    await _setup(hass, setup_ec, override=OVERRIDE)

    await _motion(hass)
    await _set(hass, OVERRIDE, "on")
    assert ec_state(hass) == "overridden"

    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "overridden"
    assert calls.turned_off() == []

    # Light still on when the override ends: EC treats it as a fresh activation.
    await _set(hass, OVERRIDE, "off")
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"
    assert len(calls.turned_off(LIGHT)) == 1


async def test_override_custom_state_strings(
    hass: HomeAssistant, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    hass.states.async_set(OVERRIDE, "off")
    hass.states.async_set(TV, "idle")
    await _setup(
        hass, setup_ec, overrides=[OVERRIDE, TV], override_states_on=["on", "playing"]
    )

    await _set(hass, TV, "playing")
    assert ec_state(hass) == "overridden"
    await _set(hass, TV, "paused")
    assert ec_state(hass) == "idle"

    await _set(hass, OVERRIDE, "on")
    assert ec_state(hass) == "overridden"
    # Both overrides have to be off before EC is enabled again.
    await _set(hass, TV, "playing")
    await _set(hass, OVERRIDE, "off")
    assert ec_state(hass) == "overridden"
    await _set(hass, TV, "paused")
    assert ec_state(hass) == "idle"


# Stay mode


@pytest.mark.xfail(
    strict=True,
    reason="The timer still runs in stay mode and raises MachineError when it expires",
)
async def test_stay_mode(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC, caplog
) -> None:
    await _setup(hass, setup_ec, stay_mode=True)

    await _motion(hass)
    assert ec_state(hass) == "active_stay_on"
    assert len(calls.turned_on(LIGHT)) == 1

    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "active_stay_on"
    assert calls.turned_off() == []
    assert "MachineError" not in caplog.text

    # Only a manual off ends it.
    await _set(hass, LIGHT, "off")
    assert ec_state(hass) == "idle"


async def test_stay_mode_services(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)

    await hass.services.async_call(
        DOMAIN, "enable_stay_mode", {"entity_id": ENTITY_ID}, blocking=True
    )
    await _motion(hass)
    assert ec_state(hass) == "active_stay_on"
    await _set(hass, LIGHT, "off")
    assert ec_state(hass) == "idle"

    await hass.services.async_call(
        DOMAIN, "disable_stay_mode", {"entity_id": ENTITY_ID}, blocking=True
    )
    await _motion(hass)
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"


# Duration sensors


@pytest.mark.parametrize(
    "config", [{"sensor_type": "duration"}, {"sensor_type_duration": True}]
)
async def test_duration_sensor_off_before_timer(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC, config
) -> None:
    await _setup(hass, setup_ec, **config)
    assert hass.states.get(ENTITY_ID).attributes["sensor_type"] == "duration"

    await _set(hass, SENSOR, "on")
    await advance(hass, freezer, 2)
    await _set(hass, SENSOR, "off")
    # The timer still runs from when the sensor turned on.
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, DELAY - 2 + 1)
    assert ec_state(hass) == "idle"
    assert len(calls.turned_off(LIGHT)) == 1


async def test_duration_sensor_on_past_timer(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec, sensor_type="duration")

    await _set(hass, SENSOR, "on")
    await advance(hass, freezer, DELAY * 3)
    assert ec_state(hass) == "active_timer"
    assert hass.states.get(ENTITY_ID).attributes["expires_at"] == "pending sensor"
    assert calls.turned_off() == []

    await _set(hass, SENSOR, "off")
    assert ec_state(hass) == "idle"
    assert len(calls.turned_off(LIGHT)) == 1


async def test_duration_sensor_resets_timer(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec, sensor_type="duration", sensor_resets_timer=True)

    await _set(hass, SENSOR, "on")
    await advance(hass, freezer, 3)
    await _set(hass, SENSOR, "off")
    # The full delay starts again from the sensor turning off.
    await advance(hass, freezer, DELAY - 1)
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, 2)
    assert ec_state(hass) == "idle"

    # Same when the sensor stays on past the delay.
    await _set(hass, SENSOR, "on")
    await advance(hass, freezer, DELAY * 3)
    await _set(hass, SENSOR, "off")
    await advance(hass, freezer, DELAY - 1)
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, 2)
    assert ec_state(hass) == "idle"


# Backoff


async def test_backoff(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(
        hass, setup_ec, delay=4, backoff=True, backoff_factor=2, backoff_max=10
    )

    await _motion(hass)
    assert hass.states.get(ENTITY_ID).attributes["delay"] == "4s"
    await _motion(hass)
    assert hass.states.get(ENTITY_ID).attributes["delay"] == "8s"
    await _motion(hass)
    # 16s, capped by backoff_max.
    assert hass.states.get(ENTITY_ID).attributes["delay"] == "10s"
    assert hass.states.get(ENTITY_ID).attributes["backoff_count"] == 2

    await advance(hass, freezer, 9)
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, 2)
    assert ec_state(hass) == "idle"

    # The next activation starts from the configured delay again.
    await _motion(hass)
    assert hass.states.get(ENTITY_ID).attributes["delay"] == "4s"
    await advance(hass, freezer, 5)
    assert ec_state(hass) == "idle"
