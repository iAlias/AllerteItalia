"""Parsing the MIMIT CSVs, including the rows that are not well behaved."""

from custom_components.allerte_italia.sources.fuel import (
    cheapest,
    parse_prices,
    parse_stations,
)

# Catania, roughly.
HOME_LAT = 37.5079
HOME_LON = 15.0830

STATIONS_CSV = [
    "Estrazione del 2026-08-27",
    "idImpianto|Gestore|Bandiera|Tipo Impianto|Nome Impianto|Indirizzo|Comune|Provincia|Latitudine|Longitudine",
    # ~1 km away
    "1001|Gestore Uno|Agip Eni|Stradale|Stazione Centro|Via Etnea 1|CATANIA|CT|37.5150|15.0870",
    # ~200 km away, in Palermo
    "1002|Gestore Due|Q8|Stradale|Stazione Lontana|Via Roma 2|PALERMO|PA|38.1157|13.3615",
    # broken coordinates
    "1003|Gestore Tre|IP|Stradale|Stazione Rotta|Via Tre|CATANIA|CT|non-un-numero|15.09",
    # too few fields
    "1004|Gestore Quattro|Esso",
    "",
]

PRICES_CSV = [
    "Estrazione del 2026-08-27",
    "idImpianto|descCarburante|prezzo|isSelf|dtComu",
    "1001|Benzina|1.899|1|26/08/2026 12:30:07",
    "1001|Gasolio|1.749|1|26/08/2026 12:30:09",
    "1001|Gasolio|1.849|0|26/08/2026 12:30:09",
    # a station we filtered out
    "1002|Benzina|1.999|1|26/08/2026 12:30:07",
    # comma decimal separator
    "1001|GPL|0,699|1|26/08/2026 12:30:11",
    # unparseable price
    "1001|Metano|n/d|1|26/08/2026 12:30:12",
]


class TestParseStations:
    def test_keeps_only_stations_inside_the_radius(self):
        stations = parse_stations(STATIONS_CSV, HOME_LAT, HOME_LON, radius_km=10)

        assert [s.station_id for s in stations] == ["1001"]

    def test_reads_the_descriptive_fields(self):
        station = parse_stations(STATIONS_CSV, HOME_LAT, HOME_LON, 10)[0]

        assert station.name == "Stazione Centro"
        assert station.brand == "Agip Eni"
        assert station.town == "CATANIA"
        assert station.province == "CT"

    def test_reports_the_distance(self):
        station = parse_stations(STATIONS_CSV, HOME_LAT, HOME_LON, 10)[0]

        assert 0 < station.distance_km < 2

    def test_skips_rows_with_unreadable_coordinates(self):
        ids = [s.station_id for s in parse_stations(STATIONS_CSV, HOME_LAT, HOME_LON, 500)]

        assert "1003" not in ids

    def test_skips_truncated_rows(self):
        ids = [s.station_id for s in parse_stations(STATIONS_CSV, HOME_LAT, HOME_LON, 500)]

        assert "1004" not in ids

    def test_a_wider_radius_reaches_further(self):
        ids = [s.station_id for s in parse_stations(STATIONS_CSV, HOME_LAT, HOME_LON, 300)]

        assert "1002" in ids


class TestParsePrices:
    def test_keeps_only_the_requested_stations(self):
        prices = parse_prices(PRICES_CSV, station_ids={"1001"})

        assert {p.station_id for p in prices} == {"1001"}

    def test_can_filter_by_fuel_type(self):
        prices = parse_prices(PRICES_CSV, {"1001"}, fuel_types=["Gasolio"])

        assert {p.fuel for p in prices} == {"Gasolio"}

    def test_distinguishes_self_service_from_attended(self):
        prices = parse_prices(PRICES_CSV, {"1001"}, fuel_types=["Gasolio"])

        assert sorted(p.self_service for p in prices) == [False, True]

    def test_accepts_a_comma_as_decimal_separator(self):
        prices = parse_prices(PRICES_CSV, {"1001"}, fuel_types=["GPL"])

        assert prices[0].price == 0.699

    def test_skips_prices_that_are_not_numbers(self):
        prices = parse_prices(PRICES_CSV, {"1001"}, fuel_types=["Metano"])

        assert prices == []


class TestCheapest:
    def test_finds_the_lowest_price_for_a_fuel(self):
        prices = parse_prices(PRICES_CSV, {"1001"})

        assert cheapest(prices, "Gasolio").price == 1.749

    def test_returns_nothing_when_the_fuel_is_absent(self):
        prices = parse_prices(PRICES_CSV, {"1001"})

        assert cheapest(prices, "Cherosene") is None
