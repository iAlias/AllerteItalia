"""Constants for the Allerte Italia integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "allerte_italia"

# --- Sources ---------------------------------------------------------------

MIMIT_PRICES_URL: Final = (
    "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"
)
MIMIT_STATIONS_URL: Final = (
    "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
)
INGV_EVENTS_URL: Final = "https://webservices.ingv.it/fdsnws/event/1/query"
DPC_CRITICALITY_URL: Final = (
    "https://raw.githubusercontent.com/pcm-dpc/"
    "DPC-Bollettini-Criticita-Idrogeologica-Idraulica/master/files"
)

# --- Update intervals ------------------------------------------------------
# Each source moves at its own pace: prices change once a day, quakes need to be
# timely, bulletins are issued a couple of times a day.

SCAN_INTERVAL_FUEL: Final = timedelta(hours=12)
SCAN_INTERVAL_QUAKES: Final = timedelta(minutes=5)
SCAN_INTERVAL_ALERTS: Final = timedelta(hours=1)
SCAN_INTERVAL_HEAT: Final = timedelta(minutes=30)

# The station registry rarely changes; refetching it daily is wasteful.
STATIONS_MAX_AGE: Final = timedelta(days=7)

# --- Configuration keys ----------------------------------------------------

CONF_RADIUS_FUEL: Final = "radius_fuel"
CONF_RADIUS_QUAKES: Final = "radius_quakes"
CONF_FUEL_TYPES: Final = "fuel_types"
CONF_ALERT_TOWN: Final = "alert_town"

CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_FUEL_ENABLED: Final = "fuel_enabled"
CONF_FUEL_THRESHOLD: Final = "fuel_threshold"
CONF_QUAKE_ENABLED: Final = "quake_enabled"
CONF_QUAKE_MIN_MAGNITUDE: Final = "quake_min_magnitude"
CONF_ALERT_ENABLED: Final = "alert_enabled"
CONF_ALERT_MIN_LEVEL: Final = "alert_min_level"
CONF_HEAT_ENABLED: Final = "heat_enabled"
CONF_HEAT_THRESHOLD: Final = "heat_threshold"

# --- Defaults --------------------------------------------------------------

DEFAULT_RADIUS_FUEL_KM: Final = 10.0
DEFAULT_RADIUS_QUAKES_KM: Final = 100.0
DEFAULT_QUAKE_MIN_MAGNITUDE: Final = 3.0
DEFAULT_HEAT_THRESHOLD: Final = 32.0
DEFAULT_FUEL_TYPES: Final = ["Benzina", "Gasolio"]

# --- Alert levels ----------------------------------------------------------
# Ordered from calm to severe, so a configured minimum can be compared.

ALERT_LEVELS: Final = ["verde", "giallo", "arancione", "rosso"]

# --- Anti-noise ------------------------------------------------------------

# A price bouncing around the threshold must climb this much above it before it
# can notify again.
FUEL_HYSTERESIS_EUR: Final = 0.02

# A revised quake only re-notifies if its magnitude grew by at least this much.
QUAKE_MAGNITUDE_STEP: Final = 0.5

# Minimum time between two notifications from the same source.
NOTIFY_COOLDOWN: Final = timedelta(hours=1)
