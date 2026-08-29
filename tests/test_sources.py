"""Geo maths, the INGV feed, the heat index and the DPC bulletins."""

from datetime import datetime, timezone

from custom_components.allerte_italia.geo import haversine_km, within_radius
from custom_components.allerte_italia.sources.civil_protection import (
    is_at_least,
    latest_bulletin_name,
    normalise_level,
    parse_bulletin,
    parse_zones,
    zone_for_town,
)
from custom_components.allerte_italia.sources.heat import heat_index_c, heat_level
from custom_components.allerte_italia.sources.quakes import (
    build_query,
    parse_events,
)

HOME_LAT = 37.5079
HOME_LON = 15.0830


class TestGeo:
    def test_the_distance_to_itself_is_zero(self):
        assert haversine_km(HOME_LAT, HOME_LON, HOME_LAT, HOME_LON) == 0

    def test_a_known_distance_is_about_right(self):
        # Catania to Palermo is roughly 165 km as the crow flies.
        distance = haversine_km(37.5079, 15.0830, 38.1157, 13.3615)

        assert 150 < distance < 185

    def test_within_radius_accepts_a_near_point(self):
        assert within_radius(HOME_LAT, HOME_LON, 37.515, 15.087, 10) is True

    def test_within_radius_rejects_a_far_point(self):
        assert within_radius(HOME_LAT, HOME_LON, 38.1157, 13.3615, 10) is False


class TestQuakes:
    def test_the_query_asks_the_server_to_do_the_filtering(self):
        params = build_query(
            HOME_LAT, HOME_LON, 100, 3.0, datetime(2026, 8, 28, 0, 0, 0)
        )

        assert params["maxradiuskm"] == "100"
        assert params["minmagnitude"] == "3.0"
        assert params["format"] == "geojson"

    def test_reads_an_event_from_the_feed(self):
        payload = {
            "features": [
                {
                    "properties": {
                        "eventId": 47020832,
                        "mag": 2.6,
                        "magType": "ML",
                        "time": "2026-08-28T13:09:20.140000",
                        "place": "7 km NE Coreglia Antelminelli (LU)",
                    },
                    "geometry": {"coordinates": [10.5582, 44.1203, 8.9]},
                }
            ]
        }

        events = parse_events(payload, HOME_LAT, HOME_LON)

        assert len(events) == 1
        assert events[0].event_id == "47020832"
        assert events[0].magnitude == 2.6
        assert events[0].attributes["depth_km"] == 8.9

    def test_orders_the_newest_event_first(self):
        payload = {
            "features": [
                {
                    "properties": {
                        "eventId": 1,
                        "mag": 2.0,
                        "time": "2026-08-28T10:00:00",
                        "place": "older",
                    },
                    "geometry": {"coordinates": [15.0, 37.5, 5.0]},
                },
                {
                    "properties": {
                        "eventId": 2,
                        "mag": 2.0,
                        "time": "2026-08-28T18:00:00",
                        "place": "newer",
                    },
                    "geometry": {"coordinates": [15.0, 37.5, 5.0]},
                },
            ]
        }

        events = parse_events(payload, HOME_LAT, HOME_LON)

        assert [e.event_id for e in events] == ["2", "1"]

    def test_timestamps_without_a_zone_are_treated_as_utc(self):
        payload = {
            "features": [
                {
                    "properties": {
                        "eventId": 1,
                        "mag": 3.0,
                        "time": "2026-08-28T13:09:20",
                        "place": "x",
                    },
                    "geometry": {"coordinates": [15.0, 37.5, 5.0]},
                }
            ]
        }

        assert parse_events(payload, HOME_LAT, HOME_LON)[0].occurred_at.tzinfo == timezone.utc

    def test_incomplete_features_are_skipped_not_fatal(self):
        payload = {
            "features": [
                {"properties": {"eventId": 1}, "geometry": {}},
                {"properties": {}, "geometry": {"coordinates": [15.0, 37.5]}},
                {
                    "properties": {
                        "eventId": 3,
                        "mag": 3.0,
                        "time": "2026-08-28T13:00:00",
                        "place": "good",
                    },
                    "geometry": {"coordinates": [15.0, 37.5, 5.0]},
                },
            ]
        }

        assert [e.event_id for e in parse_events(payload, HOME_LAT, HOME_LON)] == ["3"]

    def test_an_empty_feed_yields_no_events(self):
        assert parse_events({"features": []}, HOME_LAT, HOME_LON) == []


class TestHeat:
    def test_below_the_floor_it_returns_the_air_temperature(self):
        assert heat_index_c(22.0, 80) == 22.0

    def test_humid_heat_feels_hotter_than_it_is(self):
        assert heat_index_c(32.0, 70) > 32.0

    def test_dry_heat_feels_close_to_the_air_temperature(self):
        assert abs(heat_index_c(32.0, 10) - 32.0) < 4

    def test_the_level_rises_with_the_index(self):
        assert heat_level(28.0) == "verde"
        assert heat_level(31.0) == "giallo"
        assert heat_level(36.0) == "arancione"
        assert heat_level(41.0) == "rosso"


class TestCivilProtection:
    """The bulletin points at a TopoJSON; the levels and towns live there."""

    BULLETIN = {
        "name": "Bollettino del 28 agosto 2026 ore 14:38",
        "date": "2026-08-28T12:51:15.936Z",
        "today": {
            "topo_json": "https://example.invalid/20260828_1438_today.json",
            "html_descrition": "<p>…</p>",
        },
    }

    TOPOJSON = {
        "objects": {
            "20260828_1438_today": {
                "type": "GeometryCollection",
                "geometries": [
                    {
                        "properties": {
                            "Nome zona": "Sicilia or",
                            "Rappresentata nella mappa": "Allerta GIALLA",
                            "Per rischio idraulico": "NESSUNA ALLERTA",
                            "Per rischio temporali": "Allerta GIALLA",
                            "Comuni": ["Catania", "Acireale", "Misterbianco"],
                        }
                    },
                    {
                        "properties": {
                            "Nome zona": "Bacini Tordino Vomano",
                            "Rappresentata nella mappa": (
                                "Assenza di fenomeni significativi prevedibili "
                                "/ NESSUNA ALLERTA"
                            ),
                            "Comuni": ["Teramo", "Atri"],
                        }
                    },
                ],
            }
        }
    }

    def test_picks_the_most_recent_bulletin(self):
        names = ["20260827_1500.json", "20260828_1438.json", "20260828_0930.json"]

        assert latest_bulletin_name(names) == "20260828_1438.json"

    def test_ignores_files_that_are_not_bulletins(self):
        names = ["README.md", "Legenda_BCR_vert.jpg", "20260828_1438.json"]

        assert latest_bulletin_name(names) == "20260828_1438.json"

    def test_returns_nothing_when_there_are_no_bulletins(self):
        assert latest_bulletin_name(["README.md"]) is None

    def test_the_bulletin_carries_the_link_to_the_zones(self):
        bulletin = parse_bulletin(self.BULLETIN)

        assert bulletin.name.startswith("Bollettino")
        assert bulletin.topojson_url.endswith("_today.json")

    def test_reads_the_zones_out_of_the_topojson(self):
        zones = parse_zones(self.TOPOJSON)

        assert [z.name for z in zones] == ["Sicilia or", "Bacini Tordino Vomano"]

    def test_reads_the_level_of_a_zone(self):
        zones = parse_zones(self.TOPOJSON)

        assert zones[0].level == "giallo"

    def test_no_alert_reads_as_green_not_unknown(self):
        zones = parse_zones(self.TOPOJSON)

        assert zones[1].level == "verde"

    def test_keeps_the_per_risk_levels(self):
        zones = parse_zones(self.TOPOJSON)

        assert zones[0].risks["Per rischio temporali"] == "giallo"

    def test_finds_the_zone_from_a_municipality(self):
        zones = parse_zones(self.TOPOJSON)

        assert zone_for_town(zones, "Catania").name == "Sicilia or"

    def test_the_municipality_match_ignores_case(self):
        zones = parse_zones(self.TOPOJSON)

        assert zone_for_town(zones, "  cAtAnIa ").name == "Sicilia or"

    def test_falls_back_to_matching_the_zone_name(self):
        zones = parse_zones(self.TOPOJSON)

        assert zone_for_town(zones, "Sicilia or").name == "Sicilia or"

    def test_an_unknown_municipality_finds_nothing(self):
        zones = parse_zones(self.TOPOJSON)

        assert zone_for_town(zones, "Lugano") is None

    def test_level_wording_is_normalised(self):
        assert normalise_level("Allerta ROSSA") == "rosso"
        assert normalise_level("criticità gialla") == "giallo"
        assert normalise_level("NESSUNA ALLERTA") == "verde"
        assert normalise_level("qualcosa d'altro") is None

    def test_severity_comparison(self):
        assert is_at_least("arancione", "giallo") is True
        assert is_at_least("giallo", "arancione") is False
        assert is_at_least("rosso", "rosso") is True

    def test_a_malformed_topojson_yields_no_zones_rather_than_raising(self):
        assert parse_zones({"objects": "not a mapping"}) == ()

    def test_a_bulletin_without_a_zone_map_is_reported_not_guessed(self):
        assert parse_bulletin({"today": "not a mapping"}).topojson_url is None
