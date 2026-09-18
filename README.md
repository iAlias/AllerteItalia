# Allerte Italia

**Fuel prices, earthquakes, Civil Protection alerts and heat waves in Home Assistant — with notifications that fire only when you decide they should.**

[![Validate](https://github.com/iAlias/AllerteItalia/actions/workflows/validate.yml/badge.svg)](https://github.com/iAlias/AllerteItalia/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-custom-41BDF5)](https://hacs.xyz/)
[![Version](https://img.shields.io/badge/version-0.1.1-orange)](custom_components/allerte_italia/manifest.json)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

🇮🇹 [Leggi in italiano](README.it.md)

Four public Italian data sources, watched from a single integration, with thresholds you set from the UI: **no automation-writing required** to be told when diesel drops below €1.70 or the ground shakes near home.

---

## Contents

- [What it watches](#what-it-watches)
- [Installation](#installation)
- [Configuration](#configuration)
- [Why it won't spam you](#why-it-wont-spam-you)
- [Footprint on the system](#footprint-on-the-system)
- [Entities](#entities)
- [Development](#development)
- [Known limitations](#known-limitations)
- [Data sources](#data-sources)
- [License](#license)

---

## What it watches

| | Source | What you get |
|---|---|---|
| ⛽ | **MIMIT** — official prices for every filling station in Italy | Price per station and fuel type, plus the cheapest one within your chosen radius |
| 🌍 | **INGV** — Italy's national seismological service | The latest earthquake's magnitude, location, depth and distance from you |
| ⚠️ | **Civil Protection** (Protezione Civile) — criticality bulletins | Your zone's alert level: green, yellow, orange, red |
| 🌡️ | **Heat index** | Perceived temperature computed from data Home Assistant already has |

---

## Installation

**HACS** → Integrations → ⋮ menu → *Custom repositories* → add
`https://github.com/iAlias/AllerteItalia` with category **Integration** →
install and restart Home Assistant.

Then go to *Settings → Devices & services → Add integration → Allerte Italia*.

---

## Configuration

During initial setup you choose the radius in which to search for filling stations, which fuel types you care about, the radius for earthquakes, and — if you want alerts — your Civil Protection zone.

**Notification thresholds** live in the integration's options:

| Source | Threshold | Example |
|---|---|---|
| Fuel | price below which to notify | `1.70` |
| Earthquakes | minimum magnitude | `3.5` |
| Alerts | minimum level | `orange` |
| Heat | heat index | `35` |

Notifications are sent to whichever `notify` service you point them at: your phone, Telegram, or `notify.persistent_notification` to see them inside Home Assistant.

---

## Why it won't spam you

This is the real challenge for an integration like this, and it has three distinct causes with three distinct remedies:

- **An earthquake gets republished** while INGV refines its magnitude. Events are tracked by identifier: a revision updates the sensor but does not re-notify, unless the magnitude increases significantly.
- **A price oscillates around the threshold**, between €1.699 and €1.701. After a notification, the price must first rise by a margin before it can trigger another one.
- **An orange alert lasts for days.** Notifications fire when the level changes or worsens, not on every reading, and never more than once an hour per source.

---

## Footprint on the system

The two MIMIT CSV files weigh 7.5 MB combined, but they never land in memory in full: the station registry is downloaded at most once a week and **filtered immediately** by radius — out of roughly 25,000 stations, only a few dozen remain — and prices are read line by line, discarding on the fly anything that isn't one of the selected stations.

INGV filters server-side: the response is about one kilobyte.

---

## Entities

**Sensors** — a price per station and fuel type, the cheapest per fuel type, the latest earthquake's magnitude, the alert level, the heat index.

**Binary sensors** — recent earthquake above threshold, active alert, heat alert.

Each source is independent: if MIMIT doesn't respond, earthquake data keeps flowing and only the fuel sensors become unavailable.

---

## Development

```bash
python -m pytest tests -q
```

The tests cover the pure logic — distances, CSV parsing, the heat index, feed normalization, and the three anti-spam rules — and require neither a running Home Assistant instance nor a network connection.

---

## Known limitations

- The alert zone is derived from the **municipality (comune)** you enter: the bulletin lists the municipalities in each zone, so there's no need to compute which polygon you fall in.
- Heat waves are **derived** from the heat index: Italy's Ministry of Health publishes its own bulletins only as PDFs.
- A single location — the home location configured in Home Assistant.

---

## Data sources

The data belongs to the respective agencies and remains subject to their terms:
[MIMIT](https://www.mimit.gov.it/), [INGV](https://www.ingv.it/),
[Dipartimento della Protezione Civile](https://github.com/pcm-dpc).

---

## License

[MIT](LICENSE) © 2026 iAlias
