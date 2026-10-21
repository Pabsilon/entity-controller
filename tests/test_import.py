"""Entity Controllers imported from YAML into config entries."""

from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.entity_controller.const import DOMAIN

from .conftest import (
    STARTUP_DELAY,
    ServiceCalls,
    advance,
    ec_state,
    setup_at_boot,
)

ENTITY_ID = f"{DOMAIN}.room"
SENSOR = "binary_sensor.motion"
LIGHT = "light.room"
CONFIG = {"sensor": SENSOR, "entity": LIGHT, "delay": 5}
OPTIONS = {"sensors": [SENSOR], "entities": [LIGHT], "delay": 5}


@pytest.fixture(autouse=True)
def initial_states(hass: HomeAssistant) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")


async def _boot(hass: HomeAssistant, config: dict[str, Any]) -> None:
    """Start HA with `config` as its configuration.yaml."""
    hass.set_state(CoreState.not_running)
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()
    hass.set_state(CoreState.running)


def _issue(hass: HomeAssistant, issue_id: str) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


async def test_yaml_is_imported(hass: HomeAssistant) -> None:
    await setup_at_boot(hass, {"room": CONFIG})

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.source == SOURCE_IMPORT
    assert entry.unique_id == "room"
    assert entry.title == "room"
    assert entry.data == {"object_id": "room"}
    # Legacy keys are saved under the names the options form uses.
    assert entry.options == OPTIONS

    entity_entry = er.async_get(hass).async_get(ENTITY_ID)
    assert entity_entry.config_entry_id == entry.entry_id
    assert ec_state(hass) == "pending"


async def test_friendly_name_keeps_entity_id(hass: HomeAssistant) -> None:
    await setup_at_boot(hass, {"hall": {**CONFIG, "friendly_name": "Upstairs Hall"}})

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.unique_id == "hall"
    assert entry.title == "Upstairs Hall"
    assert "friendly_name" not in entry.options
    state = hass.states.get(f"{DOMAIN}.upstairs_hall")
    assert state.attributes["friendly_name"] == "Upstairs Hall"


async def test_import_drops_unknown_keys_and_defaults(hass: HomeAssistant) -> None:
    config = {
        **CONFIG,
        "sensors": ["binary_sensor.other", SENSOR],
        "sensor_type_duration": True,
        "stay_mode": False,
        "not_an_option": 1,
        "night_mode": {"start_time": "22:00:00", "end_time": "06:00:00", "typo": 1},
        "behaviours": {"on_enter_idle": "off"},
    }
    await setup_at_boot(hass, {"room": config})

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert dict(entry.options) == {
        **OPTIONS,
        "sensors": [SENSOR, "binary_sensor.other"],
        "sensor_type": "duration",
        "night_mode": {"start_time": "22:00:00", "end_time": "06:00:00"},
    }


async def test_restart_does_not_import_again(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_IMPORT,
        title="room",
        unique_id="room",
        data={"object_id": "room"},
        options=OPTIONS,
    )
    entry.add_to_hass(hass)

    # Changes to the YAML after the import are ignored.
    await setup_at_boot(hass, {"room": {**CONFIG, "delay": 60}})

    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    assert entry.options == OPTIONS
    assert ec_state(hass) == "pending"


async def test_yaml_raises_deprecation_issue(hass: HomeAssistant) -> None:
    await setup_at_boot(hass, {"room": CONFIG})
    issue = _issue(hass, "deprecated_yaml")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING


async def test_without_yaml_issues_are_removed(hass: HomeAssistant) -> None:
    for issue_id in ("deprecated_yaml", "yaml_conflict_room"):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=issue_id,
        )

    await _boot(hass, {})

    assert _issue(hass, "deprecated_yaml") is None
    assert _issue(hass, "yaml_conflict_room") is None


async def test_name_taken_by_ui_ec_is_not_imported(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_USER,
        title="Room",
        unique_id="room",
        options={**OPTIONS, "delay": 30},
    )
    entry.add_to_hass(hass)

    await setup_at_boot(hass, {"room": CONFIG})

    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    assert entry.options == {**OPTIONS, "delay": 30}
    issue = _issue(hass, "yaml_conflict_room")
    assert issue is not None
    assert issue.translation_placeholders == {"key": "room", "title": "Room"}


@pytest.mark.parametrize("source", ["yaml", "entry"])
async def test_yaml_and_entry_behave_the_same(
    hass: HomeAssistant, freezer, calls: ServiceCalls, source: str
) -> None:
    if source == "yaml":
        await setup_at_boot(hass, {"room": CONFIG})
    else:
        MockConfigEntry(
            domain=DOMAIN, title="room", unique_id="room", options=OPTIONS
        ).add_to_hass(hass)
        await _boot(hass, {})
    calls.register()
    await advance(hass, freezer, STARTUP_DELAY + 1)
    calls.clear()

    assert ec_state(hass) == "idle"
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert ec_state(hass) == "active_timer"
    assert len(calls.turned_on(LIGHT)) == 1

    hass.states.async_set(SENSOR, "off")
    await advance(hass, freezer, 6)
    assert ec_state(hass) == "idle"
    assert len(calls.turned_off(LIGHT)) == 1
