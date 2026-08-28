"""Turning source updates into notifications, sparingly.

The gates in `thresholds` decide whether something is worth saying; this module
decides how to say it and sends it through the notify service the user chose.
Gate state is kept in memory and restored from the config entry, so a restart
does not replay notifications that were already sent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant

from .const import (
    ALERT_LEVELS,
    CONF_ALERT_ENABLED,
    CONF_ALERT_MIN_LEVEL,
    CONF_FUEL_ENABLED,
    CONF_FUEL_THRESHOLD,
    CONF_HEAT_ENABLED,
    CONF_HEAT_THRESHOLD,
    CONF_NOTIFY_SERVICE,
    CONF_QUAKE_ENABLED,
    CONF_QUAKE_MIN_MAGNITUDE,
    DEFAULT_HEAT_THRESHOLD,
    DEFAULT_QUAKE_MIN_MAGNITUDE,
    FUEL_HYSTERESIS_EUR,
    NOTIFY_COOLDOWN,
    QUAKE_MAGNITUDE_STEP,
)
from .sources.base import SourceResult
from .thresholds import EventGate, LevelGate, ValueGate

_LOGGER = logging.getLogger(__name__)


class NotificationManager:
    """Holds the gates and sends what survives them."""

    def __init__(self, hass: HomeAssistant, options: dict) -> None:
        self._hass = hass
        self._options = options
        self._service = options.get(CONF_NOTIFY_SERVICE)

        self._fuel_gates: dict[str, ValueGate] = {}
        self._quake_gate = EventGate(
            min_magnitude=float(
                options.get(CONF_QUAKE_MIN_MAGNITUDE, DEFAULT_QUAKE_MIN_MAGNITUDE)
            ),
            magnitude_step=QUAKE_MAGNITUDE_STEP,
            cooldown=NOTIFY_COOLDOWN,
        )
        self._alert_gate = LevelGate(
            levels=ALERT_LEVELS,
            min_level=options.get(CONF_ALERT_MIN_LEVEL, "giallo"),
        )
        self._heat_gate = ValueGate(
            threshold=-float(options.get(CONF_HEAT_THRESHOLD, DEFAULT_HEAT_THRESHOLD)),
            cooldown=NOTIFY_COOLDOWN,
        )

    async def async_process(self, source: str, result: SourceResult) -> None:
        """Look at one refresh and notify if it crossed something."""
        if not self._service or not result.available:
            return

        now = datetime.now(timezone.utc)

        if source == "fuel" and self._options.get(CONF_FUEL_ENABLED):
            await self._async_process_fuel(result, now)
        elif source == "quakes" and self._options.get(CONF_QUAKE_ENABLED):
            await self._async_process_quakes(result, now)
        elif source == "alerts" and self._options.get(CONF_ALERT_ENABLED):
            await self._async_process_alerts(result)
        elif source == "heat" and self._options.get(CONF_HEAT_ENABLED):
            await self._async_process_heat(result, now)

    async def _async_process_fuel(self, result: SourceResult, now: datetime) -> None:
        threshold = self._options.get(CONF_FUEL_THRESHOLD)
        if threshold is None:
            return

        for measurement in result.measurements:
            if not measurement.key.startswith("cheapest_"):
                continue

            gate = self._fuel_gates.setdefault(
                measurement.key,
                ValueGate(
                    threshold=float(threshold),
                    hysteresis=FUEL_HYSTERESIS_EUR,
                    cooldown=NOTIFY_COOLDOWN,
                ),
            )
            if not gate.evaluate(measurement.value, now).notify:
                continue

            fuel = measurement.attributes.get("fuel", "carburante")
            station = measurement.attributes.get("station") or "un distributore"
            town = measurement.attributes.get("town") or ""
            await self._async_send(
                title=f"{fuel} a {measurement.value:.3f} €/L",
                message=(
                    f"{fuel} sceso a {measurement.value:.3f} €/L "
                    f"presso {station}" + (f" ({town})" if town else "")
                ),
            )

    async def _async_process_quakes(self, result: SourceResult, now: datetime) -> None:
        current_ids = {event.event_id for event in result.events}
        self._quake_gate.forget_before(current_ids)

        for event in result.events:
            if not self._quake_gate.evaluate(event.event_id, event.magnitude, now).notify:
                continue

            distance = event.attributes.get("distance_km")
            where = event.description or "località non indicata"
            await self._async_send(
                title=f"Terremoto M{event.magnitude}",
                message=(
                    f"Magnitudo {event.magnitude} — {where}"
                    + (f", a {distance} km da te" if distance is not None else "")
                ),
            )

    async def _async_process_alerts(self, result: SourceResult) -> None:
        if result.level is None:
            return
        if not self._alert_gate.evaluate(result.level).notify:
            return

        bulletin = ""
        if result.measurements:
            bulletin = result.measurements[0].attributes.get("bulletin") or ""

        await self._async_send(
            title=f"Allerta {result.level}",
            message=f"Protezione Civile: allerta {result.level}. {bulletin}".strip(),
        )

    async def _async_process_heat(self, result: SourceResult, now: datetime) -> None:
        if not result.measurements:
            return
        index = result.measurements[0].value

        # ValueGate fires on the way down; heat matters on the way up, so both
        # the threshold and the reading are negated to reuse the same rule.
        if not self._heat_gate.evaluate(-index, now).notify:
            return

        await self._async_send(
            title=f"Caldo: indice {index} °C",
            message=(
                f"L'indice di calore ha raggiunto {index} °C "
                f"({result.level}). Bevi e evita le ore centrali."
            ),
        )

    async def _async_send(self, title: str, message: str) -> None:
        domain, _, service = str(self._service).partition(".")
        if not domain or not service:
            _LOGGER.warning("Invalid notify service: %s", self._service)
            return

        try:
            await self._hass.services.async_call(
                domain, service, {"title": title, "message": message}, blocking=False
            )
        except Exception as err:  # noqa: BLE001 - a bad service must not break refresh
            _LOGGER.warning("Could not send notification: %s", err)
