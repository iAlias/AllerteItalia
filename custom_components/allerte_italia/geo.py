"""Distance maths, kept free of Home Assistant so it can be tested alone."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance in kilometres between two points.

    Accurate enough for "is this petrol station within 10 km", which is all the
    integration asks of it.
    """
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def within_radius(
    lat1: float, lon1: float, lat2: float, lon2: float, radius_km: float
) -> bool:
    """True when the second point lies within radius_km of the first."""
    return haversine_km(lat1, lon1, lat2, lon2) <= radius_km
