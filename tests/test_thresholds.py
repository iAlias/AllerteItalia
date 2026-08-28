"""The anti-noise rules, which are where this integration becomes a nuisance."""

from datetime import datetime, timedelta

from custom_components.allerte_italia.const import ALERT_LEVELS
from custom_components.allerte_italia.thresholds import (
    EventGate,
    LevelGate,
    ValueGate,
)

NOW = datetime(2026, 8, 29, 12, 0, 0)


class TestValueGate:
    def test_notifies_when_the_value_drops_below_the_threshold(self):
        gate = ValueGate(threshold=1.70)

        assert gate.evaluate(1.68, NOW).notify is True

    def test_stays_silent_while_the_value_is_above(self):
        gate = ValueGate(threshold=1.70)

        assert gate.evaluate(1.75, NOW).notify is False

    def test_does_not_notify_twice_for_the_same_crossing(self):
        gate = ValueGate(threshold=1.70)
        gate.evaluate(1.68, NOW)

        assert gate.evaluate(1.67, NOW + timedelta(hours=2)).notify is False

    def test_a_value_bouncing_inside_the_band_does_not_rearm(self):
        gate = ValueGate(threshold=1.70, hysteresis=0.02)
        gate.evaluate(1.69, NOW)

        # Back above the threshold, but not clear of the band.
        gate.evaluate(1.71, NOW + timedelta(hours=1))

        assert gate.evaluate(1.69, NOW + timedelta(hours=2)).notify is False

    def test_climbing_clear_of_the_band_rearms_the_gate(self):
        gate = ValueGate(threshold=1.70, hysteresis=0.02)
        gate.evaluate(1.69, NOW)
        gate.evaluate(1.75, NOW + timedelta(hours=1))

        assert gate.evaluate(1.69, NOW + timedelta(hours=2)).notify is True

    def test_cooldown_holds_back_a_second_notification(self):
        gate = ValueGate(threshold=1.70, cooldown=timedelta(hours=6))
        gate.evaluate(1.68, NOW)
        gate.armed = True  # a genuine new crossing

        assert gate.evaluate(1.60, NOW + timedelta(hours=1)).notify is False

    def test_after_the_cooldown_it_notifies_again(self):
        gate = ValueGate(threshold=1.70, cooldown=timedelta(hours=6))
        gate.evaluate(1.68, NOW)
        gate.armed = True

        assert gate.evaluate(1.60, NOW + timedelta(hours=7)).notify is True


class TestEventGate:
    def test_notifies_for_an_event_above_the_minimum(self):
        gate = EventGate(min_magnitude=3.0)

        assert gate.evaluate("ev1", 3.4, NOW).notify is True

    def test_ignores_an_event_below_the_minimum(self):
        gate = EventGate(min_magnitude=3.0)

        assert gate.evaluate("ev1", 2.1, NOW).notify is False

    def test_a_republished_event_does_not_notify_again(self):
        gate = EventGate(min_magnitude=3.0, magnitude_step=0.5)
        gate.evaluate("ev1", 3.4, NOW)

        # The network refines the magnitude slightly.
        assert gate.evaluate("ev1", 3.6, NOW + timedelta(minutes=5)).notify is False

    def test_a_sizeable_upgrade_notifies_again(self):
        gate = EventGate(min_magnitude=3.0, magnitude_step=0.5)
        gate.evaluate("ev1", 3.4, NOW)

        assert gate.evaluate("ev1", 4.1, NOW + timedelta(minutes=5)).notify is True

    def test_an_event_that_grows_past_the_minimum_notifies(self):
        gate = EventGate(min_magnitude=3.0, magnitude_step=0.5)
        gate.evaluate("ev1", 2.4, NOW)

        assert gate.evaluate("ev1", 3.2, NOW + timedelta(minutes=5)).notify is True

    def test_forgetting_drops_events_no_longer_in_the_feed(self):
        gate = EventGate(min_magnitude=3.0)
        gate.evaluate("ev1", 3.4, NOW)
        gate.evaluate("ev2", 3.5, NOW)

        gate.forget_before({"ev2"})

        assert "ev1" not in gate.seen
        assert "ev2" in gate.seen


class TestLevelGate:
    def test_notifies_when_the_level_reaches_the_minimum(self):
        gate = LevelGate(levels=ALERT_LEVELS, min_level="giallo")

        assert gate.evaluate("giallo").notify is True

    def test_stays_silent_below_the_minimum(self):
        gate = LevelGate(levels=ALERT_LEVELS, min_level="arancione")

        assert gate.evaluate("giallo").notify is False

    def test_an_unchanged_level_does_not_notify_again(self):
        gate = LevelGate(levels=ALERT_LEVELS, min_level="giallo")
        gate.evaluate("arancione")

        assert gate.evaluate("arancione").notify is False

    def test_a_worsening_level_notifies(self):
        gate = LevelGate(levels=ALERT_LEVELS, min_level="giallo")
        gate.evaluate("giallo")

        assert gate.evaluate("rosso").notify is True

    def test_an_easing_level_does_not_notify(self):
        gate = LevelGate(levels=ALERT_LEVELS, min_level="giallo")
        gate.evaluate("rosso")

        assert gate.evaluate("giallo").notify is False

    def test_an_unknown_level_is_reported_not_guessed(self):
        gate = LevelGate(levels=ALERT_LEVELS, min_level="giallo")

        decision = gate.evaluate("viola")

        assert decision.notify is False
        assert "viola" in decision.reason
