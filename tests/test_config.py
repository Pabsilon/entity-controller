"""Config options: entity lists, triggers, service data, state strings, behaviours."""

import pytest
from homeassistant.core import HomeAssistant

from custom_components.entity_controller.const import DOMAIN

from .conftest import ServiceCalls, SetupEC, advance, ec_state

ENTITY_ID = f"{DOMAIN}.room"
SENSOR = "binary_sensor.motion"
SENSOR2 = "binary_sensor.motion2"
LIGHT = "light.room"
LIGHT2 = "light.room2"
OVERRIDE = "input_boolean.guests"
DELAY = 5


async def _motion(hass: HomeAssistant, sensor: str = SENSOR) -> None:
    hass.states.async_set(sensor, "on")
    await hass.async_block_till_done()
    hass.states.async_set(sensor, "off")
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def _initial_states(hass: HomeAssistant) -> None:
    for entity_id in (SENSOR, SENSOR2, LIGHT, LIGHT2, OVERRIDE):
        hass.states.async_set(entity_id, "off")


# Entity lists


@pytest.mark.parametrize(
    "config",
    [
        {"sensors": [SENSOR, SENSOR2], "entities": [LIGHT, LIGHT2]},
        {"sensor": SENSOR, "sensors": [SENSOR2], "entity": LIGHT, "entities": [LIGHT2]},
        {"sensor": [SENSOR, SENSOR2], "entity": [LIGHT, LIGHT2]},
    ],
    ids=["plural", "mixed", "lists_under_singular_keys"],
)
async def test_multiple_sensors_and_entities(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC, config
) -> None:
    await setup_ec({**config, "delay": DELAY})

    for sensor in (SENSOR, SENSOR2):
        calls.clear()
        await _motion(hass, sensor)
        assert ec_state(hass) == "active_timer"
        assert len(calls.turned_on(LIGHT)) == 1
        assert len(calls.turned_on(LIGHT2)) == 1

        await advance(hass, freezer, DELAY + 1)
        assert ec_state(hass) == "idle"
        assert len(calls.turned_off(LIGHT)) == 1
        assert len(calls.turned_off(LIGHT2)) == 1


async def test_any_entity_on_blocks(
    hass: HomeAssistant, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await setup_ec({"sensor": SENSOR, "entities": [LIGHT, LIGHT2], "delay": DELAY})

    await _set(hass, LIGHT2, "on")
    await _motion(hass)
    assert ec_state(hass) == "blocked"
    assert hass.states.get(ENTITY_ID).attributes["blocked_by"] == LIGHT2
    assert calls.turned_on() == []


async def test_group_uses_homeassistant_services(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    group = "group.lights"
    hass.states.async_set(group, "off")
    await setup_ec({"sensor": SENSOR, "entity": group, "delay": DELAY})

    await _motion(hass)
    assert [c.domain for c in calls.turned_on(group)] == ["homeassistant"]
    await advance(hass, freezer, DELAY + 1)
    assert [c.domain for c in calls.turned_off(group)] == ["homeassistant"]


async def test_trigger_on_activate_and_deactivate(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    """Scripts are triggered with turn_on, both when activating and deactivating."""
    await setup_ec(
        {
            "sensor": SENSOR,
            "trigger_on_activate": "script.lights_on",
            "trigger_on_deactivate": "script.lights_off",
            "delay": DELAY,
        }
    )

    await _motion(hass)
    assert ec_state(hass) == "active_timer"
    assert [c.data["entity_id"] for c in calls.calls] == ["script.lights_on"]

    calls.clear()
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"
    assert [(c.service, c.data["entity_id"]) for c in calls.calls] == [
        ("turn_on", "script.lights_off")
    ]


async def test_service_data(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await setup_ec(
        {
            "sensor": SENSOR,
            "entity": LIGHT,
            "trigger_on_activate": "script.lights_on",
            "delay": DELAY,
            "service_data": {"brightness": 128},
            "service_data_off": {"transition": 3},
        }
    )

    await _motion(hass)
    assert calls.turned_on(LIGHT)[0].data == {"entity_id": LIGHT, "brightness": 128}
    assert calls.turned_on("script.lights_on")[0].data["brightness"] == 128

    await advance(hass, freezer, DELAY + 1)
    assert calls.turned_off(LIGHT)[0].data == {"entity_id": LIGHT, "transition": 3}


# State strings


async def test_custom_sensor_states(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    sensor = "sensor.presence"
    hass.states.async_set(sensor, "clear")
    await setup_ec(
        {
            "sensor": sensor,
            "entity": LIGHT,
            "delay": DELAY,
            "sensor_states_on": ["detected"],
        }
    )

    await _set(hass, sensor, "on")
    assert ec_state(hass) == "idle"
    await _set(hass, sensor, "detected")
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"


async def test_state_strings_apply_to_every_entity_type(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await setup_ec(
        {
            "sensor": SENSOR,
            "entity": LIGHT,
            "override": OVERRIDE,
            "delay": DELAY,
            "state_strings_on": ["engaged"],
            "state_strings_off": ["disengaged"],
        }
    )

    await _set(hass, SENSOR, "engaged")
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"

    await _set(hass, OVERRIDE, "engaged")
    assert ec_state(hass) == "overridden"
    await _set(hass, OVERRIDE, "disengaged")
    assert ec_state(hass) == "idle"

    await _set(hass, LIGHT, "engaged")
    await _set(hass, SENSOR, "disengaged")
    await _set(hass, SENSOR, "engaged")
    assert ec_state(hass) == "blocked"


# Transition behaviours


async def test_default_behaviours(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    """By default only entering active (on) and entering idle (off) touch the light."""
    await setup_ec(
        {"sensor": SENSOR, "entity": LIGHT, "override": OVERRIDE, "delay": DELAY}
    )

    await _set(hass, OVERRIDE, "on")
    await _set(hass, OVERRIDE, "off")
    # Leaving overridden goes through idle, which turns the light off.
    assert [c.service for c in calls.calls] == ["turn_off"]


@pytest.mark.parametrize(
    ("behaviours", "expected_on", "expected_off"),
    [
        ({"on_enter_idle": "ignore"}, 1, 0),
        ({"on_enter_active": "ignore"}, 0, 1),
        # Exiting active and entering idle both turn the light off.
        ({"on_exit_active": "off"}, 1, 2),
        ({"on_exit_idle": "on", "on_enter_active": "ignore"}, 1, 1),
    ],
)
async def test_behaviours_on_motion(
    hass: HomeAssistant,
    freezer,
    calls: ServiceCalls,
    setup_ec: SetupEC,
    behaviours,
    expected_on,
    expected_off,
) -> None:
    await setup_ec(
        {"sensor": SENSOR, "entity": LIGHT, "delay": DELAY, "behaviours": behaviours}
    )

    await _motion(hass)
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"
    assert len(calls.turned_on(LIGHT)) == expected_on
    assert len(calls.turned_off(LIGHT)) == expected_off


async def test_behaviours_on_override(
    hass: HomeAssistant, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await setup_ec(
        {
            "sensor": SENSOR,
            "entity": LIGHT,
            "override": OVERRIDE,
            "delay": DELAY,
            "behaviours": {
                "on_enter_overridden": "on",
                "on_exit_overridden": "off",
                "on_enter_idle": "ignore",
            },
        }
    )

    await _set(hass, OVERRIDE, "on")
    assert [c.service for c in calls.calls] == ["turn_on"]
    # The light EC turned on doesn't stop it from leaving overridden.
    await _set(hass, LIGHT, "off")
    calls.clear()
    await _set(hass, OVERRIDE, "off")
    assert ec_state(hass) == "idle"
    assert [c.service for c in calls.calls] == ["turn_off"]


async def test_behaviours_on_block(
    hass: HomeAssistant, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await setup_ec(
        {
            "sensor": SENSOR,
            "entity": LIGHT,
            "delay": DELAY,
            "behaviours": {"on_enter_blocked": "on", "on_exit_blocked": "off"},
        }
    )

    await _set(hass, LIGHT, "on")
    await _motion(hass)
    assert ec_state(hass) == "blocked"
    assert [c.service for c in calls.calls] == ["turn_on"]

    calls.clear()
    await _set(hass, LIGHT, "off")
    assert ec_state(hass) == "idle"
    # on_exit_blocked, then on_enter_idle.
    assert [c.service for c in calls.calls] == ["turn_off", "turn_off"]
