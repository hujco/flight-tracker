from tracker import fetch

SAMPLE = {
    "fares": [
        {"outbound": {"departureDate": "2026-09-26T11:55:00",
                      "price": {"value": 34.99}, "flightNumber": "FR7310"}}
    ]
}
EMPTY = {"fares": []}


def test_parse_fares_tags_destination_and_origin():
    recs = fetch.parse_fares(SAMPLE, "OUT", "EFL", "BUD")
    assert recs == [{
        "origin": "BUD", "destination": "EFL", "direction": "OUT",
        "flight_date": "2026-09-26", "flight_number": "FR7310",
        "departure_time": "2026-09-26T11:55:00", "arrival_time": None,
        "price": 34.99, "currency": None,
        "price_updated": None, "previous_price": None, "seats_left": None,
    }]


def test_parse_fares_keeps_price_updated_and_times():
    payload = {"fares": [{"outbound": {
        "departureDate": "2026-09-06T05:50:00",
        "arrivalDate": "2026-09-06T08:40:00",
        "price": {"value": 49.99, "currencyCode": "EUR"},
        "priceUpdated": 1786076796000,
        "flightNumber": "FR7770"}}]}
    r = fetch.parse_fares(payload, "OUT", "PVK", "BUD")[0]
    assert r["departure_time"] == "2026-09-06T05:50:00"   # 05:50 je materialna info
    assert r["arrival_time"] == "2026-09-06T08:40:00"
    assert r["currency"] == "EUR"
    assert r["price_updated"].startswith("2026-")          # epoch ms -> ISO UTC


def test_parse_fares_skips_broken_fare_instead_of_crashing():
    # chybny zaznam nesmie zhodit cely beh (62 requestov, atomicky zapis)
    payload = {"fares": [
        {"outbound": {"departureDate": "2026-09-06T05:50:00",
                      "price": None, "flightNumber": "FR1"}},
        {"nieco_ine": {}},
        {"outbound": {"departureDate": "2026-09-06T05:50:00",
                      "price": {"value": 49.99}, "flightNumber": "FR2"}},
    ]}
    recs = fetch.parse_fares(payload, "OUT", "PVK", "BUD")
    assert [r["flight_number"] for r in recs] == ["FR2"]


def test_parse_fares_tolerates_bad_price_updated():
    payload = {"fares": [{"outbound": {
        "departureDate": "2026-09-06T05:50:00", "price": {"value": 10.0},
        "priceUpdated": "nezmysel", "flightNumber": "FR1"}}]}
    assert fetch.parse_fares(payload, "OUT", "PVK", "BUD")[0]["price_updated"] is None


def test_parse_fares_origin_defaults_none():
    recs = fetch.parse_fares(SAMPLE, "OUT", "EFL")
    assert recs[0]["origin"] is None


def test_parse_fares_empty():
    assert fetch.parse_fares(EMPTY, "RET", "ZTH") == []


def test_days_in_month_september():
    days = fetch.days_in_month(2026, 9)
    assert len(days) == 30 and days[0] == "2026-09-01" and days[-1] == "2026-09-30"


class FakeResp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p


class FakeSession:
    def __init__(self, by_day):
        self.by_day = by_day
        self.calls = []
    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        return FakeResp(self.by_day.get(params["outboundDepartureDateFrom"], EMPTY))


def test_fetch_leg_tags_destination_origin_and_iterates():
    sess = FakeSession({"2026-09-26": SAMPLE})
    recs = fetch.fetch_leg("VIE", "PVK", "OUT", "PVK", "VIE", 2026, 9, session=sess)
    assert len(sess.calls) == 30
    assert len(recs) == 1
    assert recs[0]["destination"] == "PVK"
    assert recs[0]["origin"] == "VIE"
    assert sess.calls[0]["departureAirportIataCode"] == "VIE"
    assert sess.calls[0]["arrivalAirportIataCode"] == "PVK"


def test_fetch_fixed_leg_only_given_days():
    sess = FakeSession({"2026-09-06": SAMPLE})
    recs = fetch.fetch_fixed_leg("BUD", "EFL", "OUT", "EFL", "BUD",
                                 ["2026-09-06", "2026-09-01"], session=sess)
    # len 2 zadané dni sa fetchujú (nie celý mesiac)
    assert len(sess.calls) == 2
    assert {c["outboundDepartureDateFrom"] for c in sess.calls} == {"2026-09-06", "2026-09-01"}
    assert len(recs) == 1 and recs[0]["origin"] == "BUD" and recs[0]["destination"] == "EFL"
