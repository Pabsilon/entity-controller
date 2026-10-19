"""Night mode and start/end time constraints."""

from datetime import datetime

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.entity_controller.const import DOMAIN

from .conftest import ServiceCalls, SetupEC, advance, ec_state

ENTITY_ID = f"{DOMAIN}.room"
SENSOR = "binary_sensor.motion"
LIGHT = "light.room"
DELAY = 5
NIGHT_DELAY = 2
NIGHT_MODE = {
    "start_time": "20:00:00",
    "end_time": "06:00:00",
    "delay": NIGHT_DELAY,
    "service_data": {"brightness": 20},
}


async def _setup(hass: HomeAssistant, setup_ec: SetupEC, **config) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await setup_ec({"sensor": SENSOR, "entity": LIGHT, "delay": DELAY, **config})


async def _motion(hass: HomeAssistant) -> None:
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    hass.states.async_set(SENSOR, "off")
    await hass.async_block_till_done()


@pytest.fixture(autouse=True, params=["America/Los_Angeles", "Pacific/Auckland"])
async def time_zone(hass: HomeAssistant, request) -> None:
    """Run every test in two zones, one of them a day ahead of UTC."""
    await hass.config.async_set_time_zone(request.param)


async def _move_to(hass: HomeAssistant, freezer, when: str) -> None:
    """Move the clock to `when`, a local time in HA's time zone."""
    local = datetime.fromisoformat(when).replace(tzinfo=dt_util.get_default_time_zone())
    freezer.move_to(local)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


# Night mode


@pytest.mark.parametrize(
    ("now", "mode", "brightness", "delay"),
    [
        ("2026-10-19 12:00:00", "day", 200, DELAY),
        ("2026-10-19 21:00:00", "night", 20, NIGHT_DELAY),
        # The night window spans midnight.
        ("2026-10-19 03:00:00", "night", 20, NIGHT_DELAY),
    ],
)
async def test_night_mode(
    hass: HomeAssistant,
    freezer,
    calls: ServiceCalls,
    setup_ec: SetupEC,
    now: str,
    mode: str,
    brightness: int,
    delay: int,
) -> None:
    await _move_to(hass, freezer, now)
    await _setup(
        hass, setup_ec, night_mode=NIGHT_MODE, service_data={"brightness": 200}
    )

    await _motion(hass)
    assert calls.turned_on(LIGHT)[0].data["brightness"] == brightness
    assert hass.states.get(ENTITY_ID).attributes["mode"] == mode

    await advance(hass, freezer, delay - 1)
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, 2)
    assert ec_state(hass) == "idle"


async def test_night_mode_follows_the_clock(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _move_to(hass, freezer, "2026-10-19 19:55:00")
    await _setup(hass, setup_ec, night_mode=NIGHT_MODE)

    await _motion(hass)
    assert "brightness" not in calls.turned_on(LIGHT)[0].data
    await advance(hass, freezer, DELAY + 1)

    await _move_to(hass, freezer, "2026-10-19 20:00:01")
    calls.clear()
    await _motion(hass)
    assert calls.turned_on(LIGHT)[0].data["brightness"] == 20
    await advance(hass, freezer, NIGHT_DELAY + 1)
    assert ec_state(hass) == "idle"


async def test_night_mode_service_data_off(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _move_to(hass, freezer, "2026-10-19 21:00:00")
    await _setup(
        hass,
        setup_ec,
        night_mode={**NIGHT_MODE, "service_data_off": {"transition": 10}},
        service_data_off={"transition": 1},
    )

    await _motion(hass)
    await advance(hass, freezer, NIGHT_DELAY + 1)
    assert calls.turned_off(LIGHT)[0].data["transition"] == 10


async def test_set_night_mode_service(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _move_to(hass, freezer, "2026-10-19 12:00:00")
    await _setup(hass, setup_ec, night_mode=NIGHT_MODE)

    await hass.services.async_call(
        DOMAIN,
        "set_night_mode",
        {"entity_id": ENTITY_ID, "start_time": "11:00:00", "end_time": "13:00:00"},
        blocking=True,
    )
    await _motion(hass)
    assert calls.turned_on(LIGHT)[0].data["brightness"] == 20
    await advance(hass, freezer, NIGHT_DELAY + 1)
    assert ec_state(hass) == "idle"

    # Without times, night mode collapses to midnight.
    await hass.services.async_call(
        DOMAIN, "set_night_mode", {"entity_id": ENTITY_ID}, blocking=True
    )
    calls.clear()
    await _motion(hass)
    assert "brightness" not in calls.turned_on(LIGHT)[0].data
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"


# Constraints

WINDOW = {"start_time": "08:00:00", "end_time": "20:00:00"}


async def test_constrained_outside_window(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _move_to(hass, freezer, "2026-10-19 21:00:00")
    await _setup(hass, setup_ec, **WINDOW)
    await advance(hass, freezer, 2)
    assert ec_state(hass) == "constrained"

    await _motion(hass)
    assert ec_state(hass) == "constrained"
    assert calls.turned_on() == []

    # The window opens the next morning.
    await _move_to(hass, freezer, "2026-10-20 08:00:01")
    assert ec_state(hass) == "idle"
    await _motion(hass)
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"

    # ...and closes again in the evening.
    await _move_to(hass, freezer, "2026-10-20 20:00:01")
    assert ec_state(hass) == "constrained"


async def test_not_constrained_inside_window(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _move_to(hass, freezer, "2026-10-19 12:00:00")
    await _setup(hass, setup_ec, **WINDOW)
    await advance(hass, freezer, 2)
    assert ec_state(hass) == "idle"

    await _move_to(hass, freezer, "2026-10-19 20:00:01")
    assert ec_state(hass) == "constrained"


async def test_window_closing_leaves_light_on(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _move_to(hass, freezer, "2026-10-19 19:55:00")
    await _setup(hass, setup_ec, **WINDOW, delay=600)
    await _motion(hass)

    await _move_to(hass, freezer, "2026-10-19 20:00:01")
    assert ec_state(hass) == "constrained"
    assert calls.turned_off() == []

    # The light is still on when the window reopens, so EC treats it as blocked.
    await _move_to(hass, freezer, "2026-10-20 08:00:01")
    assert ec_state(hass) == "blocked"


async def test_window_closing_turns_light_off(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _move_to(hass, freezer, "2026-10-19 19:55:00")
    await _setup(
        hass, setup_ec, **WINDOW, delay=600, behaviours={"on_enter_constrained": "off"}
    )
    await _motion(hass)

    await _move_to(hass, freezer, "2026-10-19 20:00:01")
    assert ec_state(hass) == "constrained"
    assert len(calls.turned_off(LIGHT)) == 1


async def test_window_opening_runs_behaviour_once(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _move_to(hass, freezer, "2026-10-19 21:00:00")
    await _setup(
        hass,
        setup_ec,
        **WINDOW,
        behaviours={"on_exit_constrained": "on", "on_enter_idle": "ignore"},
    )
    await advance(hass, freezer, 2)
    assert ec_state(hass) == "constrained"

    await _move_to(hass, freezer, "2026-10-20 08:00:01")
    assert ec_state(hass) == "idle"
    assert len(calls.turned_on(LIGHT)) == 1


async def test_sun_based_window(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    # In London in mid October the sun rises around 07:35 and sets around 17:55.
    await hass.config.async_set_time_zone("Europe/London")
    hass.config.latitude = 51.48
    hass.config.longitude = 0.0
    window = {"start_time": "sunset - 00:30:00", "end_time": "sunrise + 00:30:00"}

    await _move_to(hass, freezer, "2026-10-19 12:00:00")
    await _setup(hass, setup_ec, **window)
    await advance(hass, freezer, 2)
    assert ec_state(hass) == "constrained"

    await _move_to(hass, freezer, "2026-10-19 18:00:00")
    assert ec_state(hass) == "idle"
