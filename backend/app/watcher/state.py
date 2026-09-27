"""The resource state machine (SRS §4.3). Pure: no database, no clock, no I/O.

    Discovered --> Watched --> Warning --> Alert --> Resolved
                      ^           |                     |
                      |        Snoozed                  |
                      +-----------+---------------------+

Only transitions produce events, and only warning/alert events notify — a resource that stays in Alert is
silent on every later sweep. Notifying every poll would send 96 messages a day.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class State(StrEnum):
    DISCOVERED = 'discovered'
    WATCHED = 'watched'
    WARNING = 'warning'
    ALERT = 'alert'
    SNOOZED = 'snoozed'
    RESOLVED = 'resolved'


class Event(StrEnum):
    WARNING = 'warning'  # approaching the limit: one gentle nudge
    ALERT = 'alert'  # limit breached: louder, with projected cost
    RESOLVED = 'resolved'  # fixed; logged for evaluation, not notified


NOTIFY = {Event.WARNING, Event.ALERT}


@dataclass(frozen=True)
class Observation:
    breached: bool  # matches the rule's policy
    approaching: bool  # matches the rule's warning variant (e.g. 75% of the age limit)


def step(current: State | None, seen: Observation, now: datetime, snoozed_until: datetime | None = None) -> tuple[State, Event | None]:
    if current is State.SNOOZED:
        if snoozed_until is not None and now < snoozed_until:
            # Silent until the timer expires — unless the problem went away on its own.
            if not seen.breached and not seen.approaching:
                return State.RESOLVED, Event.RESOLVED
            return State.SNOOZED, None
        current = State.WATCHED  # timer expired: judge afresh, so a still-breaching resource alerts again

    if seen.breached:
        return State.ALERT, (None if current is State.ALERT else Event.ALERT)

    if seen.approaching:
        if current is State.WARNING:
            return State.WARNING, None
        if current is State.ALERT:
            # Dropped back under the limit but still close — e.g. restarted. The breach is over.
            return State.WARNING, Event.RESOLVED
        return State.WARNING, Event.WARNING

    if current in (State.WARNING, State.ALERT):
        return State.RESOLVED, Event.RESOLVED
    if current is None:
        return State.DISCOVERED, None
    return State.WATCHED, None


SEVERITY = {State.ALERT: 5, State.WARNING: 4, State.SNOOZED: 3, State.WATCHED: 2, State.RESOLVED: 1, State.DISCOVERED: 0}


def worst(states) -> State:
    """A resource under several rules shows its most urgent state."""
    return max(states, key=SEVERITY.__getitem__, default=State.DISCOVERED)
