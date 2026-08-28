"""Civil Protection bulletins.

The Dipartimento della Protezione Civile publishes its hydrogeological
criticality bulletins on GitHub as JSON, refreshed by an automated pipeline
several times a day. Each bulletin points at a TopoJSON of the alert zones and
carries an HTML description per zone.

The integration does not work out which polygon the user sits in: the zone is
chosen once during setup. That keeps behaviour predictable and survives the DPC
redrawing its boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..const import ALERT_LEVELS

# Bulletin file names look like 20260828_1438.json, most recent last.
BULLETIN_NAME = re.compile(r"^(\d{8})_(\d{4})\.json$")

# The bulletins name levels in Italian; anything else is treated as unknown.
_LEVEL_WORDS = {
    "verde": "verde",
    "gialla": "giallo",
    "giallo": "giallo",
    "arancione": "arancione",
    "rossa": "rosso",
    "rosso": "rosso",
}


@dataclass(frozen=True)
class Bulletin:
    """One published bulletin, reduced to what the integration shows."""

    name: str
    published_at: datetime | None
    zone_levels: dict[str, str]


def latest_bulletin_name(names: list[str]) -> str | None:
    """Pick the most recent bulletin from a directory listing.

    The names sort chronologically as strings, which is why the format is
    checked first: a stray file must not win the comparison.
    """
    valid = [n for n in names if BULLETIN_NAME.match(n)]
    if not valid:
        return None
    return max(valid)


def parse_bulletin(payload: dict[str, Any]) -> Bulletin:
    """Read a bulletin document into name, timestamp and per-zone levels."""
    return Bulletin(
        name=str(payload.get("name") or "").strip(),
        published_at=_parse_time(payload.get("date")),
        zone_levels=_zone_levels(payload),
    )


def level_for_zone(bulletin: Bulletin, zone: str) -> str:
    """The level for one zone, defaulting to calm when it is not mentioned.

    A zone missing from the bulletin means no criticality was declared for it,
    which is green — not an error.
    """
    return bulletin.zone_levels.get(zone.casefold(), "verde")


def normalise_level(raw: str) -> str | None:
    """Map the wording used in the bulletins onto the four levels."""
    text = (raw or "").strip().casefold()
    for word, level in _LEVEL_WORDS.items():
        if word in text:
            return level
    return None


def is_at_least(level: str, minimum: str) -> bool:
    """True when level is as severe as minimum, or worse."""
    if level not in ALERT_LEVELS or minimum not in ALERT_LEVELS:
        return False
    return ALERT_LEVELS.index(level) >= ALERT_LEVELS.index(minimum)


def _zone_levels(payload: dict[str, Any]) -> dict[str, str]:
    """Zone name to level, from whichever shape the bulletin uses.

    The documents carry the zones under `today`, and describe them either as a
    list of records or as free HTML. Only the structured form is read; the HTML
    is left to the bulletin link shown to the user.
    """
    levels: dict[str, str] = {}
    today = payload.get("today")
    if not isinstance(today, dict):
        return levels

    zones = today.get("zones") or today.get("zone") or []
    if not isinstance(zones, list):
        return levels

    for entry in zones:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("zona") or entry.get("id")
        raw_level = (
            entry.get("level")
            or entry.get("livello")
            or entry.get("criticita")
            or ""
        )
        level = normalise_level(str(raw_level))
        if name and level:
            levels[str(name).strip().casefold()] = level

    return levels


def _parse_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
