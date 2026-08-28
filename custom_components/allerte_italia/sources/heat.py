"""Heat warnings, computed rather than scraped.

The Ministry of Health publishes heat-wave bulletins as PDFs only. Parsing them
would mean a heavy dependency on a fragile layout, so the warning is derived
instead from temperature and humidity, which Home Assistant already knows.

The formula is the Rothfusz heat index used by the US National Weather Service,
in Celsius. It is meaningful above roughly 27 C; below that the air temperature
is what a person feels, so that is what gets returned.
"""

from __future__ import annotations

HEAT_INDEX_FLOOR_C = 26.7  # 80 F, below which the regression is meaningless


def heat_index_c(temperature_c: float, humidity_pct: float) -> float:
    """Apparent temperature in Celsius, rounded to one decimal."""
    if temperature_c < HEAT_INDEX_FLOOR_C:
        return round(temperature_c, 1)

    humidity = max(0.0, min(100.0, humidity_pct))
    t = temperature_c * 9 / 5 + 32  # the regression is defined in Fahrenheit
    r = humidity

    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * r
        - 0.22475541 * t * r
        - 0.00683783 * t * t
        - 0.05481717 * r * r
        + 0.00122874 * t * t * r
        + 0.00085282 * t * r * r
        - 0.00000199 * t * t * r * r
    )

    # The regression overshoots in very dry or very humid heat; the NWS applies
    # these corrections to bring it back in line.
    if r < 13 and 80 <= t <= 112:
        hi -= ((13 - r) / 4) * ((17 - abs(t - 95)) / 17) ** 0.5
    elif r > 85 and 80 <= t <= 87:
        hi += ((r - 85) / 10) * ((87 - t) / 5)

    return round((hi - 32) * 5 / 9, 1)


def heat_level(index_c: float) -> str:
    """A four-step reading of the heat index, matching the alert vocabulary."""
    if index_c >= 40:
        return "rosso"
    if index_c >= 35:
        return "arancione"
    if index_c >= 30:
        return "giallo"
    return "verde"
