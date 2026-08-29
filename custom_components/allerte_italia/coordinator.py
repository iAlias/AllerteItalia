"""One coordinator per source, so a failing source cannot take the others down.

All network access lives here; the modules under `sources/` stay pure and
testable. Every fetcher returns a SourceResult and never raises: a source that
fails marks its own entities unavailable and leaves the rest of the integration
running.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ALERT_LEVELS,
    DEFAULT_QUAKE_MIN_MAGNITUDE,
    DOMAIN,
    DPC_CRITICALITY_URL,
    INGV_EVENTS_URL,
    MIMIT_PRICES_URL,
    MIMIT_STATIONS_URL,
    SCAN_INTERVAL_ALERTS,
    SCAN_INTERVAL_FUEL,
    SCAN_INTERVAL_HEAT,
    SCAN_INTERVAL_QUAKES,
    STATIONS_MAX_AGE,
)
from .sources.base import Measurement, SourceResult
from .sources.civil_protection import (
    latest_bulletin_name,
    parse_bulletin,
    parse_zones,
    zone_for_town,
)
from .sources.fuel import cheapest, parse_prices, parse_stations
from .sources.heat import heat_index_c, heat_level
from .sources.quakes import build_query, default_window, parse_events

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 60


class SourceCoordinator(DataUpdateCoordinator[SourceResult]):
    """Refreshes one source on its own schedule."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        interval: timedelta,
        fetcher: Any,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {name}",
            update_interval=interval,
        )
        self._fetcher = fetcher

    async def _async_update_data(self) -> SourceResult:
        """Never raises: a broken source reports itself, it does not cascade."""
        try:
            return await self._fetcher.async_fetch(self.hass)
        except Exception as err:  # noqa: BLE001 - a public feed can fail any way
            _LOGGER.warning("%s: refresh failed: %s", self.name, err)
            return SourceResult.unavailable(str(err))


class FuelFetcher:
    """MIMIT prices, with the station registry cached between refreshes.

    The registry is 3.5 MB and rarely changes, so it is fetched at most weekly
    and reduced immediately to the stations inside the radius.
    """

    def __init__(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        fuel_types: list[str],
    ) -> None:
        self._latitude = latitude
        self._longitude = longitude
        self._radius_km = radius_km
        self._fuel_types = fuel_types
        self._stations: list[Any] = []
        self._stations_fetched_at: datetime | None = None

    async def async_fetch(self, hass: HomeAssistant) -> SourceResult:
        await self._async_refresh_stations(hass)
        if not self._stations:
            return SourceResult.unavailable("no stations within the radius")

        station_ids = {s.station_id for s in self._stations}
        lines = await _async_fetch_lines(hass, MIMIT_PRICES_URL)
        prices = parse_prices(lines, station_ids, self._fuel_types)

        by_id = {s.station_id: s for s in self._stations}
        measurements: list[Measurement] = []

        for price in prices:
            station = by_id.get(price.station_id)
            if station is None:
                continue
            service = "self" if price.self_service else "servito"
            measurements.append(
                Measurement(
                    key=f"{price.station_id}_{price.fuel}_{service}".lower(),
                    value=price.price,
                    unit="€/L",
                    attributes={
                        "station": station.name,
                        "brand": station.brand,
                        "address": station.address,
                        "town": station.town,
                        "province": station.province,
                        "distance_km": station.distance_km,
                        "fuel": price.fuel,
                        "self_service": price.self_service,
                        "reported_at": price.reported_at,
                    },
                )
            )

        for fuel in self._fuel_types:
            best = cheapest(prices, fuel)
            if best is None:
                continue
            station = by_id.get(best.station_id)
            measurements.append(
                Measurement(
                    key=f"cheapest_{fuel}".lower(),
                    value=best.price,
                    unit="€/L",
                    attributes={
                        "fuel": fuel,
                        "station": station.name if station else None,
                        "town": station.town if station else None,
                        "distance_km": station.distance_km if station else None,
                        "self_service": best.self_service,
                    },
                )
            )

        return SourceResult(measurements=measurements)

    async def _async_refresh_stations(self, hass: HomeAssistant) -> None:
        now = datetime.now(timezone.utc)
        fresh_enough = (
            self._stations_fetched_at is not None
            and now - self._stations_fetched_at < STATIONS_MAX_AGE
        )
        if self._stations and fresh_enough:
            return

        lines = await _async_fetch_lines(hass, MIMIT_STATIONS_URL)
        self._stations = parse_stations(
            lines, self._latitude, self._longitude, self._radius_km
        )
        self._stations_fetched_at = now
        _LOGGER.debug("Kept %d stations within the radius", len(self._stations))


class QuakeFetcher:
    """Earthquakes from INGV, filtered server-side."""

    def __init__(
        self, latitude: float, longitude: float, radius_km: float, min_magnitude: float
    ) -> None:
        self._latitude = latitude
        self._longitude = longitude
        self._radius_km = radius_km
        self._min_magnitude = min_magnitude

    async def async_fetch(self, hass: HomeAssistant) -> SourceResult:
        session = async_get_clientsession(hass)
        params = build_query(
            self._latitude,
            self._longitude,
            self._radius_km,
            # Ask a little below the notification threshold, so the sensor can
            # show a nearby tremor that is not worth waking anyone for.
            max(1.0, self._min_magnitude - DEFAULT_QUAKE_MIN_MAGNITUDE + 1.0),
            default_window(datetime.now(timezone.utc)),
        )

        async with session.get(
            INGV_EVENTS_URL, params=params, timeout=REQUEST_TIMEOUT
        ) as response:
            if response.status == 204:
                # FDSN answers 204 when nothing matched; that is not an error.
                return SourceResult(events=[])
            response.raise_for_status()
            payload = await response.json(content_type=None)

        events = parse_events(payload, self._latitude, self._longitude)
        return SourceResult(events=events)


class AlertFetcher:
    """Civil Protection criticality bulletins.

    The zones and their levels live in a 1.2 MB TopoJSON referenced by the
    bulletin, so it is downloaded only when a new bulletin is published rather
    than on every hourly poll.
    """

    def __init__(self, town: str) -> None:
        self._town = town
        self._bulletin_name: str | None = None
        self._zones: tuple[Any, ...] = ()

    async def async_fetch(self, hass: HomeAssistant) -> SourceResult:
        session = async_get_clientsession(hass)
        listing_url = (
            "https://api.github.com/repos/pcm-dpc/"
            "DPC-Bollettini-Criticita-Idrogeologica-Idraulica/contents/files"
        )

        async with session.get(listing_url, timeout=REQUEST_TIMEOUT) as response:
            response.raise_for_status()
            listing = await response.json(content_type=None)

        names = [item.get("name", "") for item in listing if isinstance(item, dict)]
        latest = latest_bulletin_name(names)
        if latest is None:
            return SourceResult.unavailable("no bulletin published")

        async with session.get(
            f"{DPC_CRITICALITY_URL}/{latest}", timeout=REQUEST_TIMEOUT
        ) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)

        bulletin = parse_bulletin(payload)

        if latest != self._bulletin_name or not self._zones:
            if not bulletin.topojson_url:
                return SourceResult.unavailable("bulletin has no zone map")
            async with session.get(
                bulletin.topojson_url, timeout=REQUEST_TIMEOUT
            ) as response:
                response.raise_for_status()
                topojson = await response.json(content_type=None)
            self._zones = parse_zones(topojson)
            self._bulletin_name = latest

        zone = zone_for_town(self._zones, self._town)
        if zone is None:
            return SourceResult.unavailable(
                f"'{self._town}' is not listed in any alert zone"
            )

        return SourceResult(
            level=zone.level,
            measurements=[
                Measurement(
                    key="alert_level",
                    value=float(ALERT_LEVELS.index(zone.level)),
                    unit="",
                    attributes={
                        "level": zone.level,
                        "zone": zone.name,
                        "town": self._town,
                        "bulletin": bulletin.name,
                        "published_at": (
                            bulletin.published_at.isoformat()
                            if bulletin.published_at
                            else None
                        ),
                        **zone.risks,
                    },
                )
            ],
        )


class HeatFetcher:
    """Heat index derived from entities Home Assistant already has."""

    def __init__(self, temperature_entity: str, humidity_entity: str) -> None:
        self._temperature_entity = temperature_entity
        self._humidity_entity = humidity_entity

    async def async_fetch(self, hass: HomeAssistant) -> SourceResult:
        temperature = _numeric_state(hass, self._temperature_entity)
        humidity = _numeric_state(hass, self._humidity_entity)

        if temperature is None or humidity is None:
            return SourceResult.unavailable(
                "temperature or humidity entity is unavailable"
            )

        index = heat_index_c(temperature, humidity)
        level = heat_level(index)

        return SourceResult(
            level=level,
            measurements=[
                Measurement(
                    key="heat_index",
                    value=index,
                    unit="°C",
                    attributes={
                        "level": level,
                        "temperature": temperature,
                        "humidity": humidity,
                    },
                )
            ],
        )


async def _async_fetch_lines(hass: HomeAssistant, url: str) -> list[str]:
    """Download a CSV and hand back its lines.

    aiohttp buffers the body anyway, so the saving that matters is not keeping
    the parsed rows: the parsers discard everything outside the radius as they
    iterate, which is where the memory would otherwise go.
    """
    session = async_get_clientsession(hass)
    async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        text = await response.text(encoding="utf-8", errors="replace")
    return text.splitlines()


def _numeric_state(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", ""):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def build_coordinators(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, SourceCoordinator]:
    """Create the coordinators enabled by this config entry."""
    from .const import (  # local import keeps the module import graph shallow
        CONF_ALERT_TOWN,
        CONF_FUEL_TYPES,
        CONF_QUAKE_MIN_MAGNITUDE,
        CONF_RADIUS_FUEL,
        CONF_RADIUS_QUAKES,
        DEFAULT_FUEL_TYPES,
        DEFAULT_RADIUS_FUEL_KM,
        DEFAULT_RADIUS_QUAKES_KM,
    )

    data = {**entry.data, **entry.options}
    latitude = hass.config.latitude
    longitude = hass.config.longitude

    coordinators: dict[str, SourceCoordinator] = {
        "fuel": SourceCoordinator(
            hass,
            "fuel",
            SCAN_INTERVAL_FUEL,
            FuelFetcher(
                latitude,
                longitude,
                float(data.get(CONF_RADIUS_FUEL, DEFAULT_RADIUS_FUEL_KM)),
                list(data.get(CONF_FUEL_TYPES, DEFAULT_FUEL_TYPES)),
            ),
        ),
        "quakes": SourceCoordinator(
            hass,
            "quakes",
            SCAN_INTERVAL_QUAKES,
            QuakeFetcher(
                latitude,
                longitude,
                float(data.get(CONF_RADIUS_QUAKES, DEFAULT_RADIUS_QUAKES_KM)),
                float(data.get(CONF_QUAKE_MIN_MAGNITUDE, DEFAULT_QUAKE_MIN_MAGNITUDE)),
            ),
        ),
    }

    town = data.get(CONF_ALERT_TOWN)
    if town:
        coordinators["alerts"] = SourceCoordinator(
            hass, "alerts", SCAN_INTERVAL_ALERTS, AlertFetcher(town)
        )

    temperature_entity = data.get("temperature_entity")
    humidity_entity = data.get("humidity_entity")
    if temperature_entity and humidity_entity:
        coordinators["heat"] = SourceCoordinator(
            hass,
            "heat",
            SCAN_INTERVAL_HEAT,
            HeatFetcher(temperature_entity, humidity_entity),
        )

    return coordinators
