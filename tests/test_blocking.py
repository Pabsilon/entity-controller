"""Blocking: EC staying out of the way of entities turned on by something else."""

from homeassistant.core import Context, HomeAssistant

from custom_components.entity_controller.const import DOMAIN

from .conftest import ServiceCalls, SetupEC, advance, ec_state

ENTITY_ID = f"{DOMAIN}.room"
SENSOR = "binary_sensor.motion"
LIGHT = "light.room"
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


async def test_light_turned_on_elsewhere_blocks_motion(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)

    hass.states.async_set(LIGHT, "on")
    await _motion(hass)
    assert ec_state(hass) == "blocked"
    assert hass.states.get(ENTITY_ID).attributes["blocked_by"] == LIGHT
    assert calls.turned_on() == []

    # Turning the light off by hand releases the block.
    hass.states.async_set(LIGHT, "off")
    await hass.async_block_till_done()
    assert ec_state(hass) == "idle"

    await _motion(hass)
    assert ec_state(hass) == "active_timer"
    assert len(calls.turned_on(LIGHT)) == 1

    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"


async def test_manual_change_while_active_blocks(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    """Someone touching the light while EC has it on hands control back to them."""
    await _setup(hass, setup_ec)

    await _motion(hass)
    assert ec_state(hass) == "active_timer"

    hass.states.async_set(LIGHT, "on", {"brightness": 10})
    await hass.async_block_till_done()
    assert ec_state(hass) == "blocked"

    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "blocked"
    assert calls.turned_off() == []


async def test_manual_off_while_active_returns_to_idle(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)

    await _motion(hass)
    hass.states.async_set(LIGHT, "off")
    await hass.async_block_till_done()
    assert ec_state(hass) == "idle"


async def test_ignored_state_attributes(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec, state_attributes_ignore=["brightness"])

    await _motion(hass)
    hass.states.async_set(LIGHT, "on", {"brightness": 10})
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"

    hass.states.async_set(LIGHT, "on", {"brightness": 10, "color_temp": 300})
    await hass.async_block_till_done()
    assert ec_state(hass) == "blocked"


async def test_ignored_event_sources(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec, ignored_event_sources=["01JIGNOREDSOURCE"])

    await _motion(hass)
    hass.states.async_set(
        LIGHT, "on", {"brightness": 10}, context=Context(id="01JIGNOREDSOURCE")
    )
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"

    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"


async def test_disable_block(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec, disable_block=True)

    # Light already on: EC takes over instead of blocking.
    hass.states.async_set(LIGHT, "on")
    await _motion(hass)
    assert ec_state(hass) == "active_timer"
    assert len(calls.turned_on(LIGHT)) == 1

    # A manual change restarts the timer rather than blocking.
    await advance(hass, freezer, DELAY - 1)
    hass.states.async_set(LIGHT, "on", {"brightness": 10})
    await advance(hass, freezer, DELAY - 1)
    assert ec_state(hass) == "active_timer"

    await advance(hass, freezer, 2)
    assert ec_state(hass) == "idle"
    assert len(calls.turned_off(LIGHT)) == 1


async def test_block_timeout(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec, block_timeout=20)

    hass.states.async_set(LIGHT, "on")
    await _motion(hass)
    assert ec_state(hass) == "blocked"

    # Motion while blocked restarts the block timeout.
    await advance(hass, freezer, 15)
    await _motion(hass)
    await advance(hass, freezer, 15)
    assert ec_state(hass) == "blocked"

    # Once it runs out, EC takes over the light and turns it off after its delay.
    await advance(hass, freezer, 6)
    assert ec_state(hass) == "active_timer"
    assert len(calls.turned_on(LIGHT)) == 1

    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"
    assert len(calls.turned_off(LIGHT)) == 1


async def test_clear_block_service(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)

    hass.states.async_set(LIGHT, "on")
    await _motion(hass)
    assert ec_state(hass) == "blocked"

    await hass.services.async_call(
        DOMAIN, "clear_block", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"
    assert len(calls.turned_on(LIGHT)) == 1

    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"


async def test_enable_block_service(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)

    # Does nothing outside active_timer.
    await hass.services.async_call(
        DOMAIN, "enable_block", {"entity_id": ENTITY_ID}, blocking=True
    )
    assert ec_state(hass) == "idle"

    await _motion(hass)
    await hass.services.async_call(
        DOMAIN, "enable_block", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert ec_state(hass) == "blocked"

    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "blocked"
    assert calls.turned_off() == []


async def test_activate_service(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    await _setup(hass, setup_ec)

    await hass.services.async_call(
        DOMAIN, "activate", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"
    assert len(calls.turned_on(LIGHT)) == 1

    # Activating again restarts the timer.
    await advance(hass, freezer, DELAY - 1)
    await hass.services.async_call(
        DOMAIN, "activate", {"entity_id": ENTITY_ID}, blocking=True
    )
    await advance(hass, freezer, DELAY - 1)
    assert ec_state(hass) == "active_timer"

    await advance(hass, freezer, 2)
    assert ec_state(hass) == "idle"


async def test_explicit_state_entities(
    hass: HomeAssistant, freezer, calls: ServiceCalls, setup_ec: SetupEC
) -> None:
    """With state_entities set, they decide blocking instead of the controlled light."""
    door = "binary_sensor.door"
    hass.states.async_set(door, "off")
    await _setup(hass, setup_ec, state_entities=[door])

    # The light being on no longer blocks.
    hass.states.async_set(LIGHT, "on")
    await _motion(hass)
    assert ec_state(hass) == "active_timer"
    await advance(hass, freezer, DELAY + 1)
    assert ec_state(hass) == "idle"

    # The state entity does.
    hass.states.async_set(door, "on")
    await _motion(hass)
    assert ec_state(hass) == "blocked"

    hass.states.async_set(door, "off")
    await hass.async_block_till_done()
    assert ec_state(hass) == "idle"
