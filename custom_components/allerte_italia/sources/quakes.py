"""Earthquakes from the INGV FDSN web service.

The service filters server-side by radius, magnitude and time window, so the
integration asks only for what it needs and gets back about a kilobyte. No
external library is involved: the response is plain GeoJSON.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..geo import haversine_km
from .base import Event


def build_query(
    latitude: float,
    longitude: float,
    radius_km: float,
    min_magnitude: float,
    since: datetime,
) -> dict[str, str]:
    """Query parameters for the FDSN endpoint."""
    return {
        "starttime": since.strftime("%Y-%m-%dT%H:%M:%S"),
        "lat": f"{latitude}",
        "lon": f"{longitude}",
        "maxradiuskm": f"{radius_km}",
        "minmagnitude": f"{min_magnitude}",
        "format": "geojson",
        "orderby": "time",
    }


def parse_events(
    payload: dict[str, Any],
    latitude: float,
    longitude: float,
) -> list[Event]:
    """Turn the GeoJSON feed into events, newest first.

    Features missing a magnitude, a time or coordinates are skipped: the feed is
    a public service and an occasional incomplete record should not break the
    whole refresh.
    """
    events: list[Event] = []

    for feature in payload.get("features", []) or []:
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []

        event_id = properties.get("eventId")
        magnitude = properties.get("mag")
        occurred_raw = properties.get("time")

        if event_id is None or magnitude is None or not occurred_raw:
            continue
        if len(coordinates) < 2:
            continue

        occurred_at = _parse_time(occurred_raw)
        if occurred_at is None:
            continue

        try:
            lon, lat = float(coordinates[0]), float(coordinates[1])
            depth = float(coordinates[2]) if len(coordinates) > 2 else None
        except (TypeError, ValueError):
            continue

        events.append(
            Event(
                event_id=str(event_id),
                magnitude=float(magnitude),
                occurred_at=occurred_at,
                description=str(properties.get("place") or "").strip(),
                attributes={
                    "magnitude_type": properties.get("magType"),
                    "depth_km": depth,
                    "latitude": lat,
                    "longitude": lon,
                    "distance_km": round(
                        haversine_km(latitude, longitude, lat, lon), 1
                    ),
                },
            )
        )

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events


def default_window(now: datetime, hours: int = 24) -> datetime:
    """The feed is asked for a rolling window rather than everything ever."""
    return now - timedelta(hours=hours)


def _parse_time(raw: str) -> datetime | None:
    """INGV timestamps are ISO without a zone; they are UTC."""
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
