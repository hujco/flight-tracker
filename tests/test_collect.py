import sqlite3
import pytest
from tracker import collect, db

SAMPLE = {
    "fares": [
        {"outbound": {"departureDate": "2026-09-26T11:55:00",
                      "price": {"value": 34.99}, "flightNumber": "FR7310"}}
    ]
}
EMPTY = {"fares": []}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, by_day):
        self.by_day = by_day
    def get(self, url, params=None, headers=None, timeout=None):
        return FakeResponse(self.by_day.get(params["outboundDepartureDateFrom"], EMPTY))


class FailingSession:
    def get(self, url, params=None, headers=None, timeout=None):
        raise RuntimeError("network down")


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


LEGS = [
    {"direction": "OUT", "origin": "VIE", "destination": "EFL"},
    {"direction": "RET", "origin": "EFL", "destination": "VIE"},
]


def test_collect_once_writes_all_legs():
    conn = make_conn()
    sess = FakeSession({"2026-09-26": SAMPLE})
    n = collect.collect_once(conn, "2026-06-30T14:00", legs=LEGS,
                             year=2026, month=9, session=sess)
    assert n == 2  # jeden let kazdym smerom (26.9.)
    rows = db.all_rows(conn)
    assert {r["direction"] for r in rows} == {"OUT", "RET"}


def test_collect_once_writes_nothing_on_failure():
    conn = make_conn()
    with pytest.raises(RuntimeError):
        collect.collect_once(conn, "2026-06-30T14:00", legs=LEGS,
                             year=2026, month=9, session=FailingSession())
    assert db.all_rows(conn) == []  # atomicita: nic sa nezapise
