"""Deciding when something is worth a notification.

This is where the integration earns its keep or becomes a nuisance, so it is
kept pure: no network, no Home Assistant, no clock of its own — the caller
passes the time in. Three separate problems, three separate defences:

* a value oscillating around its threshold  -> hysteresis
* the same event republished after revision -> identity plus a growth step
* a condition that lasts for days           -> notify on change, plus a cooldown
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class NotifyDecision:
    """Whether to notify, and why — the reason makes failures debuggable."""

    notify: bool
    reason: str


@dataclass
class ValueGate:
    """Fires when a measurement drops below a threshold, once per crossing.

    A price flickering between 1.699 and 1.701 would otherwise notify on every
    poll. After firing, the value must climb back above `threshold + hysteresis`
    before the gate is armed again.
    """

    threshold: float
    hysteresis: float = 0.0
    cooldown: timedelta = timedelta(0)
    armed: bool = True
    last_notified: datetime | None = None

    def evaluate(self, value: float, now: datetime) -> NotifyDecision:
        if value > self.threshold + self.hysteresis:
            # Comfortably above: re-arm for the next genuine crossing.
            self.armed = True
            return NotifyDecision(False, "above threshold")

        if value > self.threshold:
            # In the dead band: neither a crossing nor a re-arm.
            return NotifyDecision(False, "within hysteresis band")

        if not self.armed:
            return NotifyDecision(False, "already notified for this crossing")

        if self._in_cooldown(now):
            return NotifyDecision(False, "cooldown")

        self.armed = False
        self.last_notified = now
        return NotifyDecision(True, "crossed below threshold")

    def _in_cooldown(self, now: datetime) -> bool:
        if self.last_notified is None or not self.cooldown:
            return False
        return now - self.last_notified < self.cooldown


@dataclass
class EventGate:
    """Fires for events above a magnitude, once per event identity.

    Seismic networks republish an event while they refine its magnitude. The
    same identifier must not notify twice, unless the magnitude grew enough to
    change how alarming it is.
    """

    min_magnitude: float
    magnitude_step: float = 0.0
    cooldown: timedelta = timedelta(0)
    seen: dict[str, float] = field(default_factory=dict)
    last_notified: datetime | None = None

    def evaluate(
        self, event_id: str, magnitude: float, now: datetime
    ) -> NotifyDecision:
        if magnitude < self.min_magnitude:
            # Still remember it: a later revision may cross the threshold.
            self.seen[event_id] = max(magnitude, self.seen.get(event_id, magnitude))
            return NotifyDecision(False, "below minimum magnitude")

        previous = self.seen.get(event_id)
        if previous is not None:
            grew = magnitude - previous
            if grew < self.magnitude_step:
                self.seen[event_id] = max(previous, magnitude)
                return NotifyDecision(False, "already notified for this event")

        if self._in_cooldown(now):
            return NotifyDecision(False, "cooldown")

        self.seen[event_id] = magnitude
        self.last_notified = now
        return NotifyDecision(True, "new or upgraded event")

    def _in_cooldown(self, now: datetime) -> bool:
        if self.last_notified is None or not self.cooldown:
            return False
        return now - self.last_notified < self.cooldown

    def forget_before(self, cutoff_ids: set[str]) -> None:
        """Drop events no longer in the feed, so the map cannot grow forever."""
        for event_id in list(self.seen):
            if event_id not in cutoff_ids:
                del self.seen[event_id]


@dataclass
class LevelGate:
    """Fires when a graded condition reaches a level, once per change.

    An orange alert lasts for days; it should announce itself when it starts and
    when it worsens, not on every poll.
    """

    levels: list[str]
    min_level: str
    current: str | None = None

    def evaluate(self, level: str) -> NotifyDecision:
        if level not in self.levels:
            return NotifyDecision(False, f"unknown level: {level}")

        previous = self.current
        self.current = level

        if self._rank(level) < self._rank(self.min_level):
            return NotifyDecision(False, "below minimum level")

        if previous == level:
            return NotifyDecision(False, "unchanged")

        if previous is not None and self._rank(level) < self._rank(previous):
            # Easing off is good news, but not worth waking anyone up.
            return NotifyDecision(False, "level decreased")

        return NotifyDecision(True, "level raised")

    def _rank(self, level: str) -> int:
        return self.levels.index(level)
