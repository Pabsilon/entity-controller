"""The Entity Controller state machine.

One machine is shared by every EC: each `Model` is added to it, and the conditions
and callbacks named here are looked up on the model.
"""

from transitions.extensions import HierarchicalMachine

from .const import STATES


def build_machine() -> HierarchicalMachine:
    machine = HierarchicalMachine(
        states=STATES,
        initial="pending",
        prepare_event="prepare",
        finalize_event="finalize",
    )
    machine.add_transition(trigger="start_monitoring", source="pending", dest="idle")

    machine.add_transition(trigger="constrain", source="*", dest="constrained")
    machine.add_transition(
        trigger="override",
        source=["pending", "idle", "active_timer", "blocked"],
        dest="overridden",
    )

    machine.add_transition(
        trigger="activate", source=["idle", "blocked"], dest="active"
    )
    machine.add_transition(
        trigger="activate", source="active_timer", dest=None, after="_reset_timer"
    )

    # Idle
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="active",
        conditions=["is_state_entities_off"],
    )
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="active",
        conditions=["is_state_entities_on"],
        unless="is_block_enabled",
    )
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="blocked",
        conditions=["is_state_entities_on", "is_block_enabled"],
    )
    machine.add_transition(
        trigger="enable", source="idle", dest=None, conditions=["is_state_entities_off"]
    )

    # Blocked
    machine.add_transition(
        trigger="enable",
        source="blocked",
        dest="idle",
        conditions=["is_state_entities_off"],
    )
    # Re-entering self-transition (on_enter callback executed).
    machine.add_transition(
        trigger="sensor_on",
        source="blocked",
        dest="blocked",
        conditions=["is_block_enabled"],
    )

    # Overridden
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="idle",
        conditions=["is_state_entities_off"],
    )
    # If a device leaving overridden is on, we do not necessarily want to shut it off
    # immediately. We simply want EC to stop controlling it. To do that, we move it to
    # active, to simulate an EC trigger, and see if it exits on its own. This works for
    # event sensors, and also for duration sensors if the sensor is currently on. A
    # duration sensor that is off now will never expire on its own, so in that case
    # we assume the target is idle.
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="active",
        conditions=["is_state_entities_on", "is_event_sensor"],
    )
    # This could be duration && on, but it also works for any event sensor.
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="active",
        conditions=["is_state_entities_on", "is_sensor_on"],
    )
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="idle",
        conditions=["is_state_entities_on", "is_duration_sensor", "is_sensor_off"],
    )

    machine.add_transition(
        trigger="enter", source="active", dest="active_timer", unless="will_stay_on"
    )
    machine.add_transition(
        trigger="enter",
        source="active",
        dest="active_stay_on",
        conditions="will_stay_on",
    )

    # Active Timer
    machine.add_transition(
        trigger="sensor_on", source="active_timer", dest=None, after="_reset_timer"
    )
    machine.add_transition(
        trigger="sensor_off_duration",
        source="active_timer",
        dest="idle",
        conditions=["is_timer_expired"],
    )
    # The following two transitions must be kept separate because they have
    # special conditional logic that cannot be combined.
    machine.add_transition(
        trigger="timer_expires",
        source="active_timer",
        dest="idle",
        conditions=["is_event_sensor"],
    )
    machine.add_transition(
        trigger="timer_expires",
        source="active_timer",
        dest="idle",
        conditions=["is_duration_sensor", "is_sensor_off"],
    )
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="active",
        conditions=["is_state_entities_on", "is_event_sensor"],
    )
    # This could be duration && on, but it also works for any event sensor.
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="active",
        conditions=["is_state_entities_on", "is_sensor_on"],
    )
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="idle",
        conditions=["is_state_entities_on", "is_duration_sensor", "is_sensor_off"],
    )

    machine.add_transition(
        trigger="control",
        source="active_timer",
        dest="idle",
        conditions=["is_state_entities_off"],
    )
    machine.add_transition(
        trigger="control",
        source="active_timer",
        dest="blocked",
        conditions=["is_state_entities_on", "is_block_enabled"],
    )
    # When block is disabled, "control" resets the active timer
    machine.add_transition(
        trigger="control",
        source="active_timer",
        dest=None,
        after="_reset_timer",
        conditions=["is_state_entities_on"],
        unless="is_block_enabled",
    )
    # Manually enable blocked state
    machine.add_transition(
        trigger="block_enable",
        source="active_timer",
        dest="blocked",
        conditions=["is_state_entities_on", "is_block_enabled"],
    )

    # Active Stay On
    # The timer still runs in stay mode; its expiry is ignored.
    machine.add_transition(trigger="timer_expires", source="active_stay_on", dest=None)
    machine.add_transition(
        trigger="enable",
        source="active_stay_on",
        dest="idle",
        conditions=["is_state_entities_off"],
    )

    # Constrained
    machine.add_transition(
        trigger="enable",
        source="constrained",
        dest="idle",
        conditions=["is_override_state_off"],
    )
    machine.add_transition(
        trigger="enable",
        source="constrained",
        dest="overridden",
        conditions=["is_override_state_on"],
    )
    # Enter blocked state when component is enabled and entity is on
    machine.add_transition(
        trigger="blocked",
        source="constrained",
        dest="blocked",
        conditions=["is_block_enabled"],
    )

    return machine
