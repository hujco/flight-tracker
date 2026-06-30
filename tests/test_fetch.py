from tracker import fetch

# Skrateny realny tvar odpovede z farfnd/v4/oneWayFares
SAMPLE = {
    "fares": [
        {
            "outbound": {
                "departureDate": "2026-09-26T11:55:00",
                "arrivalDate": "2026-09-26T15:00:00",
                "price": {"value": 34.99, "currencyCode": "EUR"},
                "flightNumber": "FR7310",
            }
        }
    ]
}
EMPTY = {"fares": []}


def test_parse_fares_extracts_fields():
    recs = fetch.parse_fares(SAMPLE, "OUT")
    assert recs == [
        {
            "direction": "OUT",
            "flight_date": "2026-09-26",
            "flight_number": "FR7310",
            "price": 34.99,
            "seats_left": None,
        }
    ]


def test_parse_fares_empty():
    assert fetch.parse_fares(EMPTY, "RET") == []


def test_days_in_month_september():
    days = fetch.days_in_month(2026, 9)
    assert len(days) == 30
    assert days[0] == "2026-09-01"
    assert days[-1] == "2026-09-30"


class FakeSession:
    """Zachyti volania a vrati pripravene odpovede podla dna."""
    def __init__(self, by_day):
        self.by_day = by_day
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        return FakeResponse(self.by_day.get(params["outboundDepartureDateFrom"], EMPTY))


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_leg_iterates_all_days_and_collects():
    sess = FakeSession({"2026-09-26": SAMPLE})
    recs = fetch.fetch_leg("VIE", "EFL", "OUT", 2026, 9, session=sess)
    assert len(sess.calls) == 30           # jedno volanie na den
    assert len(recs) == 1                  # let len 26.9.
    assert recs[0]["flight_number"] == "FR7310"
    # over ze sa posielaju spravne parametre
    assert sess.calls[0]["departureAirportIataCode"] == "VIE"
    assert sess.calls[0]["arrivalAirportIataCode"] == "EFL"
    assert sess.calls[0]["outboundDepartureDateFrom"] == sess.calls[0]["outboundDepartureDateTo"]
