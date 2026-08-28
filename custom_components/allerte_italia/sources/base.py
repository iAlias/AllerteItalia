"""Shared shapes for the four sources.

The sources differ in nature: fuel prices and the heat index are continuous
measurements, quakes and bulletins are discrete events. Rather than force one
abstraction over both, the base defines the two shapes and lets each source
produce what it actually has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Measurement:
    """A number worth showing, with whatever context explains it."""

    key: str
    value: float
    unit: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    """Something that happened, identified so revisions can be recognised."""

    event_id: str
    magnitude: float
    occurred_at: datetime
    description: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceResult:
    """What one source hands back after a refresh."""

    measurements: list[Measurement] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    level: str | None = None
    available: bool = True
    error: str | None = None

    @classmethod
    def unavailable(cls, error: str) -> SourceResult:
        """A source that failed this round, without taking the others down."""
        return cls(available=False, error=error)
