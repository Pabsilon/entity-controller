"""Configuration validation."""

import logging

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.entity_controller.const import CONF_DELAY, DOMAIN

from .conftest import SetupEC, ec_state, get_entity

SENSOR = "binary_sensor.motion"
LIGHT = "light.room"
CONFIG = {"sensor": SENSOR, "entity": LIGHT}


@pytest.mark.parametrize(
    "ecs",
    [
        {"room": {**CONFIG, "delay": -1}},
        {"room": {**CONFIG, "sensor_type": "bogus"}},
        {"room": {**CONFIG, "behaviours": {"on_enter_idle": "sometimes"}}},
        {"room": {**CONFIG, "start_time": "18:00", "end_time": "06:00:00"}},
        {"room": {**CONFIG, "night_mode": {"start_time": "20:00:00"}}},
        {"room": {**CONFIG, "entity": "not an entity id"}},
        {"Living Room": CONFIG},
        {"room": {"sensor": SENSOR}},
        {"room": None},
    ],
)
async def test_invalid_config_fails_setup(hass: HomeAssistant, ecs) -> None:
    assert not await async_setup_component(hass, DOMAIN, {DOMAIN: ecs})
    assert hass.states.get(f"{DOMAIN}.room") is None


async def test_unknown_keys_warn(
    hass: HomeAssistant, setup_ec: SetupEC, caplog: pytest.LogCaptureFixture
) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    with caplog.at_level(logging.WARNING):
        await setup_ec(
            {
                **CONFIG,
                "sensor_resets_time": True,
                "night_mode": {
                    "start_time": "20:00:00",
                    "end_time": "06:00:00",
                    "dealy": 2,
                },
                "behaviours": {"on_enter_idel": "ignore"},
            }
        )

    assert ec_state(hass) == "idle"
    for key in ("sensor_resets_time", "night_mode.dealy", "behaviours.on_enter_idel"):
        assert f"room: unknown option '{key}'" in caplog.text
    assert "unknown option 'sensor'" not in caplog.text


async def test_night_mode_inherits_delay(
    hass: HomeAssistant, setup_ec: SetupEC
) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await setup_ec(
        {
            **CONFIG,
            "delay": 42,
            "night_mode": {"start_time": "20:00:00", "end_time": "06:00:00"},
        }
    )
    assert get_entity(hass).model.light_params_night[CONF_DELAY] == 42


async def test_backoff_factor_keeps_decimals(
    hass: HomeAssistant, setup_ec: SetupEC
) -> None:
    hass.states.async_set(SENSOR, "off")
    hass.states.async_set(LIGHT, "off")
    await setup_ec({**CONFIG, "backoff": True, "backoff_factor": 1.5})
    assert get_entity(hass).model.backoff_factor == 1.5
