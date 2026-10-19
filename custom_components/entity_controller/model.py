"""The state machine model: reacts to entity changes and drives the controlled entities.

The transitions between states live in `machine.py`; this holds the conditions and
callbacks they refer to by name.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import homeassistant.util.uuid as uuid_util
from homeassistant.const import CONF_NAME
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.util import dt
from transitions.extensions import HierarchicalMachine

from . import time_utils
from .const import (
    CONF_BEHAVIOURS,
    CONF_BLOCK_TIMEOUT,
    CONF_CONTROL_ENTITIES,
    CONF_CONTROL_ENTITY,
    CONF_DELAY,
    CONF_DISABLE_BLOCK,
    CONF_END_TIME,
    CONF_IGNORED_EVENT_SOURCES,
    CONF_NIGHT_MODE,
    CONF_ON_ENTER_ACTIVE,
    CONF_ON_ENTER_BLOCKED,
    CONF_ON_ENTER_CONSTRAINED,
    CONF_ON_ENTER_IDLE,
    CONF_ON_ENTER_OVERRIDDEN,
    CONF_ON_EXIT_ACTIVE,
    CONF_ON_EXIT_BLOCKED,
    CONF_ON_EXIT_CONSTRAINED,
    CONF_ON_EXIT_IDLE,
    CONF_ON_EXIT_OVERRIDDEN,
    CONF_SENSOR,
    CONF_SENSOR_RESETS_TIMER,
    CONF_SENSOR_TYPE,
    CONF_SENSOR_TYPE_DURATION,
    CONF_SENSORS,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA_OFF,
    CONF_START_TIME,
    CONF_STATE_ATTRIBUTES_IGNORE,
    CONF_STATE_ENTITIES,
    CONF_TRANSITION_BEHAVIOUR_OFF,
    CONF_TRANSITION_BEHAVIOUR_ON,
    CONF_TRIGGER_ON_ACTIVATE,
    CONF_TRIGGER_ON_DEACTIVATE,
    CONTEXT_ID_CHARACTER_LIMIT,
    DEFAULT_DELAY,
    DEFAULT_STATES_OFF,
    DEFAULT_STATES_ON,
    DEFAULT_TRANSITION_BEHAVIOURS,
    DOMAIN_SHORT,
    MODE_DAY,
    MODE_NIGHT,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
    STARTUP_DELAY,
)

if TYPE_CHECKING:
    from .entity import EntityController

# Domains that have no turn_on/turn_off services of their own and rely on
# homeassistant.turn_on/turn_off instead.
HOMEASSISTANT_TURN_ON_DOMAINS = ("group",)


class Model:
    """Represents the transitions state machine model"""

    # Set by the machine, along with the trigger and is_<state> methods
    state: str

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        machine: HierarchicalMachine,
        entity: EntityController,
    ) -> None:
        self.hass = hass
        self.entity = entity  # the entity containing this model
        self.config = config
        self.name = config.get(CONF_NAME, "Unnamed Entity Controller")
        # Named after the package rather than this module, so logger config such as
        # `custom_components.entity_controller.<name>: debug` keeps working.
        self.log = logging.getLogger(f"{__package__}.{self.name}")

        self.state_entities: list[str] = []
        self.control_entities: list[str] = []
        self.sensor_entities: list[str] = []
        self.override_entities: list[str] = []
        self.trigger_on_deactivate: list[str] = []
        self.trigger_on_activate: list[str] = []
        self.control_states_on: list[str] = []
        self.control_states_off: list[str] = []
        self.sensor_states_on: list[str] = []
        self.sensor_states_off: list[str] = []
        self.override_states_on: list[str] = []
        self.override_states_off: list[str] = []
        self.state_states_on: list[str] = []
        self.state_states_off: list[str] = []
        self.state_attributes_ignore: list[str] = []
        self.ignored_event_sources: list[str] = []

        self.timer_handle: CALLBACK_TYPE | None = None
        self.block_timer_handle: CALLBACK_TYPE | None = None
        self.start_time_event_hook: CALLBACK_TYPE | None = None
        self.end_time_event_hook: CALLBACK_TYPE | None = None
        # The configured constraint times; see the `start_time`/`end_time` properties
        self.start_time_setting: str | None = None
        self.end_time_setting: str | None = None

        self.sensor_type: str | None = None
        self.night_mode: dict[str, Any] | None = None
        self.light_params_day: dict[str, Any] = {}
        self.light_params_night: dict[str, Any] = {}
        self.light_params: dict[str, Any] = {}
        self.transition_behaviours: dict[str, str] = {}
        self.block_timeout: int | None = None
        self.disable_block = False
        self.stay = False
        self.backoff = False
        self.backoff_count = 0
        self.backoff_factor = 1.1
        self.backoff_max = 300
        self.previous_delay: float = DEFAULT_DELAY
        self.context: Context | None = None

        self.log.debug(
            "Initialising EntityController entity with this configuration: %s", config
        )

        # Added here because machine-generated methods are used by the methods below.
        machine.add_model(self)

        async_call_later(self.hass, STARTUP_DELAY, self.startup_delay_callback)

    @callback
    def startup_delay_callback(self, _now: datetime) -> None:
        config = self.config
        self.config_static_strings(config)
        self.config_control_entities(config)
        # Must come after config_control_entities (uses control entities if not set)
        self.config_state_entities(config)
        self.config_sensor_entities(config)
        self.config_override_entities(config)
        self.config_transition_behaviours(config)
        self.config_off_entities(config)
        self.config_on_entities(config)
        self.config_normal_mode(config)
        # Must come after config_normal_mode (uses normal mode parameters if not set)
        self.config_night_mode(config)
        self.config_state_attributes_ignore(config)
        self.config_times(config)
        self.config_other(config)
        self.prepare_service_data()

        if len(self.override_entities) > 0 and self.is_override_state_on():
            self.override()
            self.update(overridden_at=str(datetime.now()))
        else:
            self.start_monitoring()

    def update(self, wait: bool = False, **kwargs: Any) -> None:
        """Called from different methods to report a state attribute change"""
        for k, v in kwargs.items():
            if v is not None:
                self.entity.set_attr(k, v)

        if not wait:
            self.entity.do_update()

    def finalize(self) -> None:
        self.entity.do_update()

    # =====================================================
    # S T A T E   C H A N G E   C A L L B A C K S
    # =====================================================

    @callback
    def sensor_state_change(self, event: Event[EventStateChangedData]) -> None:
        """State change callback for sensor entities"""
        entity = event.data["entity_id"]
        old = event.data["old_state"]
        new = event.data["new_state"]
        self.log.debug(
            "sensor_state_change :: %10s Sensor state change to: %s", entity, new.state
        )
        self.log.debug("sensor_state_change :: state: %s", self.state)

        if old is not None and new.state == old.state:
            self.log.debug("sensor_state_change :: Ignore attribute only change")
            return

        if new.state in self.sensor_states_on and (
            self.is_idle() or self.is_active_timer() or self.is_blocked()
        ):
            self.set_context(new.context)
            self.update(last_triggered_by=entity)
            self.sensor_on()

        if (
            new.state in self.sensor_states_off
            and self.is_duration_sensor()
            and self.is_active_timer()
        ):
            self.set_context(new.context)
            self.update(last_triggered_by=entity, sensor_turned_off_at=datetime.now())

            # If configured, reset timer when duration sensor goes off
            if self.config[CONF_SENSOR_RESETS_TIMER]:
                self.log.debug("sensor_state_change :: CONF_SENSOR_RESETS_TIMER")
                self.update(
                    notes="The sensor turned off and reset the timeout. Timer started."
                )
                self._reset_timer()
            else:
                # We only care about sensor off state changes when the sensor is a
                # duration sensor and we are in active_timer state.
                self.sensor_off_duration()
                self.log.debug(
                    "sensor_state_change :: CONF_SENSOR_RESETS_TIMER - normal"
                )

    @callback
    def override_state_change(self, event: Event[EventStateChangedData]) -> None:
        """State change callback for override entities"""
        entity = event.data["entity_id"]
        old = event.data["old_state"]
        new = event.data["new_state"]
        self.log.debug(
            "override_state_change :: Override state change entity=%s, old=%s, new=%s",
            entity,
            old,
            new,
        )
        if new.state in self.override_states_on and (
            self.is_active()
            or self.is_active_timer()
            or self.is_idle()
            or self.is_blocked()
        ):
            self.set_context(new.context)
            self.update(overridden_by=entity)
            self.override()
            self.update(overridden_at=str(datetime.now()))
        if (
            new.state in self.override_states_off
            and self.is_override_state_off()
            and self.is_overridden()
        ):
            self.set_context(new.context)
            self.enable()

    @callback
    def state_entity_state_change(self, event: Event[EventStateChangedData]) -> None:
        """State change callback for state entities.

        This can be called with either a state change or an attribute change.
        """
        entity = event.data["entity_id"]
        old = event.data["old_state"]
        new = event.data["new_state"]
        self.log.debug(
            "state_entity_state_change :: [ Entity: %s, Context: %s ]\n"
            "\tOld state: %s\n\tNew State: %s",
            entity,
            new.context,
            old,
            new,
        )
        if self.is_ignored_context(new.context):
            self.log.debug(
                "state_entity_state_change :: Ignoring this state change because it "
                "came from %s",
                new.context.id,
            )
            return

        # If the state changed, we definitely want to handle the transition. If only
        # attributes changed, check whether any of them are significant (not ignored).
        if old and new and old.state == new.state:
            old_attributes = {
                k: v
                for k, v in old.attributes.items()
                if k not in self.state_attributes_ignore
            }
            new_attributes = {
                k: v
                for k, v in new.attributes.items()
                if k not in self.state_attributes_ignore
            }
            if old_attributes == new_attributes:
                self.log.debug(
                    "state_entity_state_change :: insignificant attribute change - "
                    "Ignore the state change altogether"
                )
                return
            self.log.debug(
                "state_entity_state_change :: A significant attribute changed and "
                "will be handled"
            )

        self.set_context(new.context)
        if self.is_active_timer():
            self.log.debug(
                "state_entity_state_change :: We are in active timer and the state of "
                "observed state entities changed."
            )
            self.control()

        # Checking the state avoids MachineErrors, and is cleaner than adding
        # transitions to all possible states.
        if self.is_blocked() or self.is_active_stay_on():
            self.enable()

    def _start_timer(self) -> None:
        self.log.info("_start_timer :: Light params: %s", self.light_params)
        if self.backoff_count == 0:
            self.previous_delay = self.light_params.get(CONF_DELAY, DEFAULT_DELAY)
        else:
            self.log.debug(
                "_start_timer :: Backoff: %s,  count: %s, delay%s, factor: %s",
                self.backoff,
                self.backoff_count,
                self.light_params.get(CONF_DELAY, DEFAULT_DELAY),
                self.backoff_factor,
            )
            self.previous_delay = round(self.previous_delay * self.backoff_factor, 2)
            if self.previous_delay > self.backoff_max:
                self.log.debug("Max backoff reached. Will not increase further.")
                self.previous_delay = self.backoff_max
            self.update(delay=self.previous_delay)

        expiry_time = datetime.now() + timedelta(seconds=self.previous_delay)

        # timer_handle holds the cancel callback while the timer is active, None
        # otherwise.
        self.timer_handle = async_call_later(
            self.hass, self.previous_delay, self.timer_expire
        )
        self.update(expires_at=expiry_time)

    def _cancel_timer(self) -> None:
        if self.timer_handle:
            self.timer_handle()
            self.timer_handle = None

    def _reset_timer(self) -> bool:
        self.log.debug("_reset_timer :: Resetting timer: %s", self.backoff)
        self._cancel_timer()
        self.update(reset_at=datetime.now())
        if self.backoff:
            self.backoff_count += 1
            self.update(backoff_count=self.backoff_count)
        self._start_timer()

        return True

    @callback
    def timer_expire(self, _now: datetime | None = None) -> None:
        self.log.debug("timer_expire :: Timer expired")
        self.timer_handle = None
        # A duration sensor that is still on overrides the timer
        if self.is_duration_sensor() and self.is_sensor_on():
            self.update(expires_at="pending sensor")
        else:
            self.log.debug("timer_expire :: Trigger timer_expires event")
            self.timer_expires()

    @callback
    def block_timer_expire(self, _now: datetime | None = None) -> None:
        self.log.debug("block_timer_expire :: Blocked Timer expired")
        self.block_timer_handle = None
        self.block_timer_expires()

    # =====================================================
    # S T A T E   M A C H I N E   C O N D I T I O N S
    # =====================================================

    def _first_entity_on(
        self, kind: str, entities: list[str], on_states: list[str]
    ) -> str | None:
        """Return the first of `entities` whose state is in `on_states`, if any."""
        for e in entities:
            s = self.hass.states.get(e)
            if s is None:
                self.log.error(
                    "Potential configuration error: %s Entity (%s) does not exist "
                    "(yet). Please check for spelling and typos.",
                    kind,
                    e,
                )
                continue

            if s.state in on_states:
                self.log.debug("%s entities are ON. [%s]", kind, e)
                return e
        self.log.debug("%s entities are OFF.", kind)
        return None

    def _override_entity_state(self) -> str | None:
        return self._first_entity_on(
            "Override", self.override_entities, self.override_states_on
        )

    def is_override_state_off(self) -> bool:
        return self._override_entity_state() is None

    def is_override_state_on(self) -> bool:
        return self._override_entity_state() is not None

    def _sensor_entity_state(self) -> str | None:
        return self._first_entity_on(
            "Sensor", self.sensor_entities, self.sensor_states_on
        )

    def is_sensor_off(self) -> bool:
        return self._sensor_entity_state() is None

    def is_sensor_on(self) -> bool:
        return self._sensor_entity_state() is not None

    def _state_entity_state(self) -> str | None:
        return self._first_entity_on("State", self.state_entities, self.state_states_on)

    def is_state_entities_off(self) -> bool:
        return self._state_entity_state() is None

    def is_state_entities_on(self) -> bool:
        return self._state_entity_state() is not None

    def is_block_enabled(self) -> bool:
        return self.disable_block is False

    def will_stay_on(self) -> bool:
        return self.stay

    def is_night(self) -> bool:
        if self.night_mode is None:
            return False  # if night mode is undefined, it's never night :)
        self.log.debug("NIGHT MODE ENABLED: %s", self.night_mode)
        return time_utils.now_is_between(
            self.hass,
            self.night_mode[CONF_START_TIME],
            self.night_mode[CONF_END_TIME],
        )

    def is_event_sensor(self) -> bool:
        return self.sensor_type == SENSOR_TYPE_EVENT

    def is_duration_sensor(self) -> bool:
        return self.sensor_type == SENSOR_TYPE_DURATION

    def is_timer_expired(self) -> bool:
        return self.timer_handle is None

    # =====================================================
    # S T A T E   M A C H I N E   C A L L B A C K S
    # =====================================================

    def on_enter_idle(self) -> None:
        self.log.debug("Entering idle")
        # Entering idle due to no events, set a new context with no parent
        self.set_context(None)
        self.do_transition_behaviour(CONF_ON_ENTER_IDLE)
        self.entity.reset_state()

    def on_exit_idle(self) -> None:
        self.log.debug("Exiting idle")
        self.do_transition_behaviour(CONF_ON_EXIT_IDLE)

    def on_enter_overridden(self) -> None:
        self.log.debug("Entering overridden")
        self.do_transition_behaviour(CONF_ON_ENTER_OVERRIDDEN)

    def on_exit_overridden(self) -> None:
        self.log.debug("Exiting overridden")
        self.do_transition_behaviour(CONF_ON_EXIT_OVERRIDDEN)

    def on_enter_active(self) -> None:
        self.log.debug("Entering active")
        self.update(last_triggered_at=str(datetime.now()))
        self.backoff_count = 0
        self.prepare_service_data()

        self._start_timer()

        self.log.debug(
            "on_enter_active :: light params before turning on: %s", self.light_params
        )
        self.do_transition_behaviour(CONF_ON_ENTER_ACTIVE)
        self.enter()

    def on_exit_active(self) -> None:
        self.log.debug("Exiting active")
        self.log.debug("on_exit_active :: Turning off entities, cancelling timer")
        self._cancel_timer()
        self.update(delay=self.light_params.get(CONF_DELAY))
        self.do_transition_behaviour(CONF_ON_EXIT_ACTIVE)

    def on_enter_blocked(self) -> None:
        self.log.debug("Entering blocked")
        self.update(blocked_at=datetime.now())
        self.update(blocked_by=self._state_entity_state())

        self.do_transition_behaviour(CONF_ON_ENTER_BLOCKED)
        if self.block_timeout:
            self.block_timer_handle = async_call_later(
                self.hass, self.block_timeout, self.block_timer_expire
            )
            self.update(block_timeout=self.block_timeout)

    def on_exit_blocked(self) -> None:
        self.log.debug("Exiting blocked")
        self.do_transition_behaviour(CONF_ON_EXIT_BLOCKED)
        if self.block_timer_handle:
            self.block_timer_handle()
            self.block_timer_handle = None

    def on_enter_constrained(self) -> None:
        self.log.debug("Entering constrained")
        self.do_transition_behaviour(CONF_ON_ENTER_CONSTRAINED)

    def on_exit_constrained(self) -> None:
        self.log.debug("Exiting constrained")
        self.do_transition_behaviour(CONF_ON_EXIT_CONSTRAINED)

    # =====================================================
    #    C O N F I G U R A T I O N  &  V A L I D A T I O N
    # =====================================================

    def config_transition_behaviours(self, config: dict[str, Any]) -> None:
        self.transition_behaviours = dict(DEFAULT_TRANSITION_BEHAVIOURS)
        if CONF_BEHAVIOURS in config:
            self.transition_behaviours.update(config[CONF_BEHAVIOURS])

        self.log.debug(
            "config_transition_behaviours :: Transition Behaviours: %s",
            self.transition_behaviours,
        )

    def config_control_entities(self, config: dict[str, Any]) -> None:
        self.control_entities = []
        self._add(self.control_entities, config, CONF_CONTROL_ENTITY)
        self._add(self.control_entities, config, CONF_CONTROL_ENTITIES)
        self.log.debug("Control Entities: %s", self.control_entities)

    def config_state_entities(self, config: dict[str, Any]) -> None:
        self.state_entities = []
        self._add(self.state_entities, config, CONF_STATE_ENTITIES)
        if len(self.state_entities) > 0:
            self.log.info(
                "State Entities (explicitly defined - I hope you know what you are "
                "doing): %s",
                self.state_entities,
            )
        else:
            # If no state entities are defined, use control entities as state
            self.state_entities = self.control_entities.copy()
            self.log.debug(
                "Added Control Entities as state entities (default): %s",
                self.state_entities,
            )

        async_track_state_change_event(
            self.hass, self.state_entities, self.state_entity_state_change
        )

    def config_off_entities(self, config: dict[str, Any]) -> None:
        self.trigger_on_deactivate = []
        self._add(self.trigger_on_deactivate, config, CONF_TRIGGER_ON_DEACTIVATE)
        if len(self.trigger_on_deactivate) > 0:
            self.log.info("Off Entities: %s", self.trigger_on_deactivate)

    def config_on_entities(self, config: dict[str, Any]) -> None:
        self.trigger_on_activate = []
        self._add(self.trigger_on_activate, config, CONF_TRIGGER_ON_ACTIVATE)
        if len(self.trigger_on_activate) > 0:
            self.log.info("On Entities: %s", self.trigger_on_activate)

    def config_sensor_entities(self, config: dict[str, Any]) -> None:
        self.sensor_entities = []
        self._add(self.sensor_entities, config, CONF_SENSOR)
        self._add(self.sensor_entities, config, CONF_SENSORS)

        if len(self.sensor_entities) == 0:
            self.log.error(
                "No sensor entities defined. You must define at least one sensor "
                "entity."
            )

        self.log.debug("Sensor Entities: %s", self.sensor_entities)

        async_track_state_change_event(
            self.hass, self.sensor_entities, self.sensor_state_change
        )

    def config_static_strings(self, config: dict[str, Any]) -> None:
        # One copy of the defaults is shared by every entity type, as before.
        default_on = list(DEFAULT_STATES_ON)
        default_off = list(DEFAULT_STATES_OFF)
        self.control_states_on = config.get("control_states_on", default_on)
        self.control_states_off = config.get("control_states_off", default_off)
        self.sensor_states_on = config.get("sensor_states_on", default_on)
        self.sensor_states_off = config.get("sensor_states_off", default_off)
        self.override_states_on = config.get("override_states_on", default_on)
        self.override_states_off = config.get("override_states_off", default_off)
        self.state_states_on = config.get("state_states_on", default_on)
        self.state_states_off = config.get("state_states_off", default_off)

        on = config.get("state_strings_on", False)
        if on:
            self.control_states_on.extend(on)
            self.control_states_on.extend(on)
            self.sensor_states_on.extend(on)
            self.override_states_on.extend(on)
            self.state_states_on.extend(on)

        off = config.get("state_strings_off", False)
        if off:
            self.control_states_off.extend(off)
            self.sensor_states_off.extend(off)
            self.override_states_off.extend(off)
            self.state_states_off.extend(off)

    def config_night_mode(self, config: dict[str, Any]) -> None:
        """Configure night mode parameters.

        If night mode has no service data of its own, the day mode service data is
        used instead.
        """
        if CONF_NIGHT_MODE not in config:
            return

        night_mode = config[CONF_NIGHT_MODE]
        self.night_mode = night_mode
        self.light_params_night[CONF_DELAY] = night_mode.get(
            CONF_DELAY, config.get(CONF_DELAY, DEFAULT_DELAY)
        )
        self.light_params_night[CONF_SERVICE_DATA] = night_mode.get(
            CONF_SERVICE_DATA, self.light_params_day.get(CONF_SERVICE_DATA)
        )
        self.light_params_night[CONF_SERVICE_DATA_OFF] = night_mode.get(
            CONF_SERVICE_DATA_OFF, self.light_params_day.get(CONF_SERVICE_DATA_OFF)
        )

        if CONF_START_TIME not in night_mode:
            self.log.error("Night mode requires a start_time parameter !")

        if CONF_END_TIME not in night_mode:
            self.log.error("Night mode requires a end_time parameter !")

    def config_state_attributes_ignore(self, config: dict[str, Any]) -> None:
        self._add(self.ignored_event_sources, config, CONF_IGNORED_EVENT_SOURCES)
        self._add(self.state_attributes_ignore, config, CONF_STATE_ATTRIBUTES_IGNORE)
        self.log.debug(
            "Ignoring events (state changes) caused by the following entities): %s",
            self.ignored_event_sources,
        )
        self.log.debug(
            "Ignoring state changes on the following attributes: %s",
            self.state_attributes_ignore,
        )

    def config_normal_mode(self, config: dict[str, Any]) -> None:
        self.log.info("Service data set up")
        self.light_params_day = {
            CONF_DELAY: config.get(CONF_DELAY, DEFAULT_DELAY),
            CONF_SERVICE_DATA: config.get(CONF_SERVICE_DATA, None),
            CONF_SERVICE_DATA_OFF: config.get(CONF_SERVICE_DATA_OFF, None),
        }

    @property
    def start_time(self) -> str:
        return time_utils.resolve_now_offset(self.start_time_setting)

    @property
    def end_time(self) -> str:
        return time_utils.resolve_now_offset(self.end_time_setting)

    def config_times(self, config: dict[str, Any]) -> None:
        if CONF_START_TIME in config and CONF_END_TIME in config:
            # For the `now + N (M)` debugging syntax, the initial setup uses the raw
            # value (with the first delay M)...
            self.start_time_setting = config.get(CONF_START_TIME)
            self.end_time_setting = config.get(CONF_END_TIME)
            parsed_start = time_utils.parse_time(self.hass, self.start_time)
            parsed_end = time_utils.parse_time(self.hass, self.end_time)
            # ...and later ones the normal delay N.
            sparts = re.search(r"^(now\s*[+-]\s*\d+)", config.get(CONF_START_TIME))
            if sparts is not None:
                self.start_time_setting = sparts.group(1)
            eparts = re.search(r"^(now\s*[+-]\s*\d+)", config.get(CONF_END_TIME))
            if eparts is not None:
                self.end_time_setting = eparts.group(1)

            self.update(start=self.start_time)
            self.update(end=self.end_time)

            parsed_start = time_utils.futurize(parsed_start)
            parsed_end = time_utils.futurize(parsed_end)
            self.log.debug("Setting FIRST START callback for %s", parsed_start)
            self.log.debug("Setting FIRST END callback for %s", parsed_end)

            self.start_time_event_hook = async_track_point_in_time(
                self.hass, self.start_time_callback, parsed_start
            )
            self.end_time_event_hook = async_track_point_in_time(
                self.hass, self.end_time_callback, parsed_end
            )

            if not time_utils.now_is_between(self.hass, self.start_time, self.end_time):
                self.log.debug(
                    "Constrain period active. Scheduling transition to 'constrained'"
                )
                async_call_later(self.hass, 1, self.constrain_entity)

        self.log_config()

    def config_override_entities(self, config: dict[str, Any]) -> None:
        self.override_entities = []
        self._add(self.override_entities, config, "override")
        self._add(self.override_entities, config, "overrides")

        if len(self.override_entities) > 0:
            self.log.debug("Override Entities: %s", self.override_entities)
            async_track_state_change_event(
                self.hass, self.override_entities, self.override_state_change
            )

    def config_other(self, config: dict[str, Any]) -> None:
        self.config[CONF_SENSOR_RESETS_TIMER] = config.get(CONF_SENSOR_RESETS_TIMER)

        self.block_timeout = config.get(CONF_BLOCK_TIMEOUT, None)
        self.disable_block = config.get(CONF_DISABLE_BLOCK, False)
        self.backoff = config.get("backoff", False)
        self.stay = config.get("stay_mode", False)

        if self.backoff:
            self.log.debug(
                "config_other :: setting up backoff. Using delay as initial backoff "
                "value."
            )
            self.backoff_factor = config.get("backoff_factor", 1.1)
            self.backoff_max = config.get("backoff_max", 300)

        if config.get(CONF_SENSOR_TYPE_DURATION):
            self.sensor_type = SENSOR_TYPE_DURATION
        else:
            self.sensor_type = SENSOR_TYPE_EVENT

        if CONF_SENSOR_TYPE in config:
            self.sensor_type = config.get(CONF_SENSOR_TYPE)

        self.update(sensor_type=self.sensor_type)

    # =====================================================
    #    E V E N T   C A L L B A C K S
    # =====================================================

    @callback
    def constrain_entity(self, _now: datetime) -> None:
        """Used on setup if the current time requires starting in constrained."""
        self.constrain()

    @callback
    def end_time_callback(self, _now: datetime) -> None:
        """Called at `end_time`: constrains EC and schedules the next end time."""
        self.log.debug("end_time_callback :: Triggered")
        # must be reparsed to get up to date sunset/sunrise times
        parsed_end = time_utils.futurize(
            time_utils.parse_time(self.hass, self.end_time)
        )
        self.log.debug(
            "end_time_callback :: New callback set to %s (future)", parsed_end
        )
        self.end_time_event_hook = async_track_point_in_time(
            self.hass, self.end_time_callback, parsed_end
        )
        self.update(end_time=parsed_end)

        # must be down here to make sure new callback is set regardless of exceptions
        self.do_transition_behaviour(CONF_ON_ENTER_CONSTRAINED)
        self.constrain()

    @callback
    def start_time_callback(self, _now: datetime) -> None:
        """Called at `start_time`: enables EC and schedules the next start time."""
        self.log.debug("start_time_callback :: Triggered")
        # must be reparsed to get up to date sunset/sunrise times
        parsed_start = time_utils.futurize(
            time_utils.parse_time(self.hass, self.start_time)
        )
        self.log.debug(
            "start_time_callback :: New callback set to %s (future)", parsed_start
        )
        self.start_time_event_hook = async_track_point_in_time(
            self.hass, self.start_time_callback, parsed_start
        )

        self.update(start_time=parsed_start)

        if self.is_state_entities_on() and self.is_block_enabled():
            self.blocked()
        else:
            # If the entity is on and block is disabled, we just transition from
            # constrained to idle and leave the entity on. (Don't start a timer to
            # turn it off.)
            self.enable()
        self.do_transition_behaviour(CONF_ON_EXIT_CONSTRAINED)

    # =====================================================
    #    H E L P E R   F U N C T I O N S
    # =====================================================

    def _call_with_service_data(
        self, entities: list[str], service: str, data_key: str
    ) -> None:
        """Call `service` on each entity, with the current light params' `data_key`."""
        service_data = self.light_params.get(data_key)
        for e in entities:
            if service_data is not None:
                self.log.debug(
                    "Calling %s on %s with service parameters %s",
                    service,
                    e,
                    service_data,
                )
                self.call_service(e, service, **service_data)
            else:
                self.log.debug(
                    "Calling %s on %s (no parameters provided to pass to service call)",
                    service,
                    e,
                )
                self.call_service(e, service)

    def turn_on_control_entities(self) -> None:
        # Entities defined outside of control entities via `trigger_on_activate`.
        self._call_with_service_data(
            self.trigger_on_activate, "turn_on", CONF_SERVICE_DATA
        )
        self._call_with_service_data(
            self.control_entities, "turn_on", CONF_SERVICE_DATA
        )

    def turn_off_control_entities(self) -> None:
        # Entities defined outside of control entities via `trigger_on_deactivate`.
        # They are triggered, so they get turn_on rather than turn_off.
        self._call_with_service_data(
            self.trigger_on_deactivate, "turn_on", CONF_SERVICE_DATA_OFF
        )
        self._call_with_service_data(
            self.control_entities, "turn_off", CONF_SERVICE_DATA_OFF
        )

    def prepare_service_data(self) -> None:
        """Pick the day or night service parameters.

        Called when entering active state and on initial set up.
        """
        if self.is_night():
            self.log.debug("Using NIGHT MODE parameters: %s", self.light_params_night)
            self.light_params = self.light_params_night
            self.update(mode=MODE_NIGHT)
        else:
            self.log.debug("Using DAY MODE parameters: %s", self.light_params_day)
            self.light_params = self.light_params_day
            if self.night_mode is not None:
                self.update(mode=MODE_DAY)  # only show when night mode set up
        self.update(delay=self.light_params.get(CONF_DELAY))

    def call_service(self, entity: str, service: str, **service_data: Any) -> None:
        """Helper for calling HA services with the correct parameters"""
        self.log.debug("call_service :: Calling service %s on %s", service, entity)

        domain = entity.split(".")[0]
        if (
            service in ("turn_on", "turn_off")
            and domain in HOMEASSISTANT_TURN_ON_DOMAINS
        ):
            domain = "homeassistant"
            self.log.debug(
                "call_service :: Actually calling service %s on %s via the %s domain "
                "because the entity domain requires it.",
                service,
                entity,
                domain,
            )

        service_data["entity_id"] = entity
        self.hass.async_create_task(
            self.hass.services.async_call(
                domain, service, service_data, context=self.context
            )
        )
        self.update(service_data=service_data)

    def set_context(self, parent: Context | None = None) -> None:
        """Set the context used when calling other services.

        The new ID is linked to the context (`parent`) of the triggering event
        and will be unique per trigger.
        """
        # Unique name per EC instance, but short enough to fit within id length
        name_hash = hashlib.sha1(self.name.encode("UTF-8")).hexdigest()[:6]
        unique_id = uuid_util.random_uuid_hex()

        # Restrict id length to database field size
        context_id = f"{DOMAIN_SHORT}_{name_hash}_{unique_id}"[
            :CONTEXT_ID_CHARACTER_LIMIT
        ]
        self.log.debug("set_context :: context_id: %s", context_id)
        # parent_id only exists for a non-None parent
        parent_id = parent.id if parent else None
        self.context = Context(parent_id=parent_id, id=context_id)
        # Set the EC entity's context so the logbook can identify the source of
        # events that will be generated by this object.
        self.entity.async_set_context(self.context)

    def is_ignored_context(self, context: Context) -> bool:
        """Should the event with the given `context` be ignored?"""
        if any(
            re.match(pattern + r"\b", context.id) is not None
            for pattern in self.ignored_event_sources
        ):
            # Matched an ignore_event_source regex pattern
            return True
        # Otherwise, ignore only EC-generated events
        return context.id.startswith(f"{DOMAIN_SHORT}_")

    def _add(self, target: list[str], config: dict[str, Any], key: str) -> None:
        """Add the value of `config[key]` (a string or a list) to `target`."""
        self.log.debug("add :: Adding config key `%s` to the config list", key)
        v = config.get(key)

        if isinstance(v, str):
            target.append(v)
        elif isinstance(v, list):
            target.extend(v)
        elif v is None:
            self.log.debug("Config key %s not provided by user. Skipping.", key)
        else:
            self.log.error(
                "Cannot determine type of provided config value. Key: %s, Type: %s, "
                "Value: %s",
                key,
                type(v),
                v,
            )

    def log_config(self) -> None:
        self.log.debug("--------------------------------------------------")
        self.log.debug("       C O N F I G U R A T I O N   D U M P        ")
        self.log.debug("--------------------------------------------------")
        self.log.debug("Entity Controller       %s", self.name)
        self.log.debug("Sensor Entities         %s", self.sensor_entities)
        self.log.debug("Control Entities:       %s", self.control_entities)
        self.log.debug("State Entities:         %s", self.state_entities)
        self.log.debug("Activate Trigger E.:    %s", self.trigger_on_activate)
        self.log.debug("Deactivate Trigger E.:  %s", self.trigger_on_deactivate)
        self.log.debug("Ignored state attrs:    %s", self.state_attributes_ignore)
        self.log.debug("Light params:           %s", self.light_params)
        self.log.debug("        -------        Time        -------        ")
        self.log.debug("Start time:             %s", self.start_time_setting)
        self.log.debug("End time:               %s", self.end_time_setting)
        self.log.debug("DT Now:                 %s", dt.now())
        self.log.debug("datetime Now:           %s", datetime.now())
        self.log.debug("Next Sunrise:           %s", time_utils.next_sunrise(self.hass))
        self.log.debug("Next Sunset:            %s", time_utils.next_sunset(self.hass))
        self.log.debug("        -------        Sun         -------        ")
        self.log.debug("Sunrise:                %s", time_utils.sunrise(self.hass))
        self.log.debug("Sunset:                 %s", time_utils.sunset(self.hass))
        self.log.debug("Transition Behaviours: %s", self.transition_behaviours)
        self.log.debug("--------------------------------------------------")

    def do_transition_behaviour(self, behaviour: str) -> None:
        """Act on the configured behaviour for a state transition."""
        action = self.transition_behaviours.get(behaviour)
        self.log.debug("%10s | Performing Transition Behaviour: %s", behaviour, action)
        if action == CONF_TRANSITION_BEHAVIOUR_ON:
            self.turn_on_control_entities()
        if action == CONF_TRANSITION_BEHAVIOUR_OFF:
            self.turn_off_control_entities()
