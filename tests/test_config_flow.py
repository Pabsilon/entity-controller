"""Entity Controllers set up from config entries (the UI)."""

from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.entity_controller import DATA
from custom_components.entity_controller.const import DOMAIN

from .conftest import STARTUP_DELAY, ServiceCalls, advance, ec_state, get_entity

ENTITY_ID = f"{DOMAIN}.living_room"
SENSOR = "binary_sensor.motion"
LIGHT = "light.room"
OPTIONS = {"sensors": [SENSOR], "entities": [LIGHT], "delay": 5}


@pytest.fixture(autouse=True)
def fake_services(calls: ServiceCalls) -> None:
    calls.register()


def _entry(**options: Any) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Living Room",
        unique_id="living_room",
        options={**OPTIONS, **options},
    )


async def _add_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_user_flow_creates_entry(
    hass: HomeAssistant, freezer, calls: ServiceCalls
) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Living Room", "sensors": [SENSOR], "entities": [LIGHT], "delay": 5},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room"
    assert result["options"] == OPTIONS
    entry = result["result"]
    assert entry.unique_id == "living_room"
    await hass.async_block_till_done()

    entity_entry = er.async_get(hass).async_get(ENTITY_ID)
    assert entity_entry is not None
    assert entity_entry.unique_id == entry.entry_id
    assert entity_entry.config_entry_id == entry.entry_id

    # HA is already running, so there is no startup delay.
    await advance(hass, freezer, 1)
    assert ec_state(hass, ENTITY_ID) == "idle"
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert ec_state(hass, ENTITY_ID) == "active_timer"
    assert len(calls.turned_on(LIGHT)) == 1


async def test_user_flow_duplicate_name_aborts(hass: HomeAssistant) -> None:
    await _add_entry(hass, _entry())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "living room", "sensors": [SENSOR], "entities": [LIGHT], "delay": 5},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_invalid_name(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": " !! ", "sensors": [SENSOR], "entities": [LIGHT], "delay": 5},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"name": "invalid_name"}


async def test_entry_at_boot_waits_startup_delay(hass: HomeAssistant, freezer) -> None:
    hass.set_state(CoreState.not_running)
    await _add_entry(hass, _entry())
    hass.set_state(CoreState.running)

    await advance(hass, freezer, STARTUP_DELAY - 1)
    assert ec_state(hass, ENTITY_ID) == "pending"
    await advance(hass, freezer, 2)
    assert ec_state(hass, ENTITY_ID) == "idle"


async def test_unload_entry(hass: HomeAssistant, freezer) -> None:
    entry = _entry()
    await _add_entry(hass, entry)
    await advance(hass, freezer, 1)
    model = get_entity(hass, ENTITY_ID).model

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert get_entity(hass, ENTITY_ID) is None
    assert model not in hass.data[DATA].machine.models
    assert model._unsubs == []
    assert model.timer_handle is None


async def test_options_change_reloads_entry(hass: HomeAssistant, freezer) -> None:
    entry = _entry()
    await _add_entry(hass, entry)
    await advance(hass, freezer, 1)
    assert get_entity(hass, ENTITY_ID).model.light_params_day["delay"] == 5

    hass.config_entries.async_update_entry(entry, options={**OPTIONS, "delay": 30})
    await hass.async_block_till_done()
    await advance(hass, freezer, 1)
    assert ec_state(hass, ENTITY_ID) == "idle"
    assert get_entity(hass, ENTITY_ID).model.light_params_day["delay"] == 30


async def test_set_night_mode_does_not_change_options(
    hass: HomeAssistant, freezer
) -> None:
    night_mode = {"start_time": "20:00:00", "end_time": "06:00:00"}
    entry = _entry(night_mode=night_mode)
    await _add_entry(hass, entry)
    await advance(hass, freezer, 1)

    await hass.services.async_call(
        DOMAIN,
        "set_night_mode",
        {"entity_id": ENTITY_ID, "start_time": "21:00:00"},
        blocking=True,
    )
    assert get_entity(hass, ENTITY_ID).model.night_mode["start_time"] == "21:00:00"
    assert entry.options["night_mode"] == night_mode
