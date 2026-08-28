"""Fuel prices from the MIMIT open data.

Two pipe-separated CSVs, 7.5 MB between them, published every morning. Home
Assistant often runs on a Raspberry Pi, so neither file is ever held in memory:
both are parsed line by line and everything outside the configured radius is
discarded as it goes. Of ~25,000 stations, a handful survive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from ..geo import haversine_km

# Both files start with a line like "Estrazione del 2026-08-27" before the
# header, which is why the first two lines are skipped rather than one.
PREAMBLE_LINES = 2

STATION_FIELDS = 10
PRICE_FIELDS = 5


@dataclass(frozen=True)
class Station:
    """A petrol station near enough to care about."""

    station_id: str
    name: str
    brand: str
    address: str
    town: str
    province: str
    latitude: float
    longitude: float
    distance_km: float


@dataclass(frozen=True)
class Price:
    """One fuel price at one station."""

    station_id: str
    fuel: str
    price: float
    self_service: bool
    reported_at: str


def parse_stations(
    lines: Iterable[str],
    latitude: float,
    longitude: float,
    radius_km: float,
) -> list[Station]:
    """Keep only the stations within radius_km, reading the file as a stream.

    Malformed rows are skipped rather than aborting the file: a single bad line
    in a 25,000-row public dataset should not cost the user their sensors.
    """
    stations: list[Station] = []

    for row in _rows(lines, STATION_FIELDS):
        try:
            lat = float(row[8])
            lon = float(row[9])
        except (ValueError, IndexError):
            continue

        distance = haversine_km(latitude, longitude, lat, lon)
        if distance > radius_km:
            continue

        stations.append(
            Station(
                station_id=row[0].strip(),
                brand=row[2].strip(),
                name=row[4].strip(),
                address=row[5].strip(),
                town=row[6].strip(),
                province=row[7].strip(),
                latitude=lat,
                longitude=lon,
                distance_km=round(distance, 2),
            )
        )

    return stations


def parse_prices(
    lines: Iterable[str],
    station_ids: set[str],
    fuel_types: Iterable[str] | None = None,
) -> list[Price]:
    """Prices for the given stations, ignoring every other row as it streams by."""
    wanted_fuels = {f.casefold() for f in fuel_types} if fuel_types else None
    prices: list[Price] = []

    for row in _rows(lines, PRICE_FIELDS):
        station_id = row[0].strip()
        if station_id not in station_ids:
            continue

        fuel = row[1].strip()
        if wanted_fuels is not None and fuel.casefold() not in wanted_fuels:
            continue

        price = _to_price(row[2])
        if price is None:
            continue

        prices.append(
            Price(
                station_id=station_id,
                fuel=fuel,
                price=price,
                self_service=row[3].strip() == "1",
                reported_at=row[4].strip(),
            )
        )

    return prices


def cheapest(prices: Iterable[Price], fuel: str) -> Price | None:
    """The lowest price for one fuel, or None when nothing was found."""
    candidates = [p for p in prices if p.fuel.casefold() == fuel.casefold()]
    if not candidates:
        return None
    return min(candidates, key=lambda p: p.price)


def _rows(lines: Iterable[str], expected_fields: int) -> Iterator[list[str]]:
    """Yield well-formed rows, skipping the preamble, header and junk."""
    for index, line in enumerate(lines):
        if index < PREAMBLE_LINES:
            continue
        line = line.strip()
        if not line:
            continue
        row = line.split("|")
        if len(row) < expected_fields:
            continue
        yield row


def _to_price(raw: str) -> float | None:
    """Prices normally use a dot, but a comma has been seen in the wild."""
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError:
        return None
