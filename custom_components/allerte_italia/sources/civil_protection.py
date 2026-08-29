"""Civil Protection bulletins.

The Dipartimento della Protezione Civile publishes its hydrogeological
criticality bulletins on GitHub, refreshed by an automated pipeline several
times a day. The bulletin document itself carries no levels: it points at a
TopoJSON where every alert zone is a geometry whose properties hold the levels
and, usefully, the list of municipalities the zone covers.

That list is why the integration asks for a municipality rather than a zone
name: nobody knows they live in "Bacini Tordino Vomano", but everybody knows
they live in Teramo. No point-in-polygon is needed — the mapping is in the data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..const import ALERT_LEVELS

# Bulletin file names look like 20260828_1438.json, most recent last.
BULLETIN_NAME = re.compile(r"^(\d{8})_(\d{4})\.json$")

# The property holding the overall level shown on the map, plus the per-risk
# ones, in the order they are reported.
LEVEL_PROPERTY = "Rappresentata nella mappa"
RISK_PROPERTIES = (
    "Per rischio idraulico",
    "Per rischio temporali",
    "Per rischio idrogeologico",
)
ZONE_PROPERTY = "Nome zona"
TOWNS_PROPERTY = "Comuni"

# The bulletins spell levels out in Italian. "Nessuna allerta" is the calm
# case and must be recognised, or a quiet day would read as unknown.
_LEVEL_WORDS = (
    ("rossa", "rosso"),
    ("rosso", "rosso"),
    ("arancione", "arancione"),
    ("gialla", "giallo"),
    ("giallo", "giallo"),
    ("verde", "verde"),
    ("nessuna allerta", "verde"),
)


@dataclass(frozen=True)
class Zone:
    """One alert zone, with the levels declared for it today."""

    name: str
    level: str
    risks: dict[str, str] = field(default_factory=dict)
    towns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Bulletin:
    """A published bulletin reduced to what the integration shows."""

    name: str
    published_at: datetime | None
    topojson_url: str | None
    zones: tuple[Zone, ...] = ()


def latest_bulletin_name(names: list[str]) -> str | None:
    """Pick the most recent bulletin from a directory listing.

    The names sort chronologically as strings, so the format is checked first:
    a stray file must not win the comparison.
    """
    valid = [n for n in names if BULLETIN_NAME.match(n)]
    if not valid:
        return None
    return max(valid)


def parse_bulletin(payload: dict[str, Any]) -> Bulletin:
    """Read the bulletin document: its name, time, and where the zones live."""
    today = payload.get("today")
    topojson_url = None
    if isinstance(today, dict):
        topojson_url = today.get("topo_json")

    return Bulletin(
        name=str(payload.get("name") or "").strip(),
        published_at=_parse_time(payload.get("date")),
        topojson_url=topojson_url,
    )


def parse_zones(topojson: dict[str, Any]) -> tuple[Zone, ...]:
    """Read every alert zone out of the TopoJSON geometries."""
    objects = topojson.get("objects")
    if not isinstance(objects, dict):
        return ()

    zones: list[Zone] = []

    for collection in objects.values():
        if not isinstance(collection, dict):
            continue
        for geometry in collection.get("geometries") or []:
            if not isinstance(geometry, dict):
                continue
            properties = geometry.get("properties")
            if not isinstance(properties, dict):
                continue

            name = str(properties.get(ZONE_PROPERTY) or "").strip()
            if not name:
                continue

            level = normalise_level(str(properties.get(LEVEL_PROPERTY) or ""))
            risks = {
                key: normalise_level(str(properties.get(key) or "")) or "verde"
                for key in RISK_PROPERTIES
                if properties.get(key)
            }
            towns = properties.get(TOWNS_PROPERTY) or []
            zones.append(
                Zone(
                    name=name,
                    level=level or "verde",
                    risks=risks,
                    towns=tuple(str(t).strip() for t in towns if t),
                )
            )

    return tuple(zones)


def zone_for_town(zones: tuple[Zone, ...], town: str) -> Zone | None:
    """The zone covering a municipality, matched case-insensitively.

    Falls back to matching the zone's own name, so someone who does know their
    zone can name it directly.
    """
    wanted = (town or "").strip().casefold()
    if not wanted:
        return None

    for zone in zones:
        if any(t.casefold() == wanted for t in zone.towns):
            return zone

    for zone in zones:
        if zone.name.casefold() == wanted:
            return zone

    return None


def normalise_level(raw: str) -> str | None:
    """Map the wording used in the bulletins onto the four levels.

    Order matters: "nessuna allerta" is checked after the colours so that a
    string mentioning both cannot be read as calm.
    """
    text = (raw or "").strip().casefold()
    if not text:
        return None
    for word, level in _LEVEL_WORDS:
        if word in text:
            return level
    return None


def is_at_least(level: str, minimum: str) -> bool:
    """True when level is as severe as minimum, or worse."""
    if level not in ALERT_LEVELS or minimum not in ALERT_LEVELS:
        return False
    return ALERT_LEVELS.index(level) >= ALERT_LEVELS.index(minimum)


def _parse_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
