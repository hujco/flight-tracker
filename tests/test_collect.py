import sqlite3
import pytest
from tracker import collect, db

SAMPLE = {"fares": [{"outbound": {"departureDate": "2026-09-26T11:55:00",
                                  "price": {"value": 34.99}, "flightNumber": "FR1"}}]}
EMPTY = {"fares": []}
DESTS = [{"code": "EFL", "label": "Kefalonia"}, {"code": "ZTH", "label": "Zakyntos"}]


class FakeResp:
    def __init__(self, p): self._p = p
    def raise_for_status(self): pass
    def json(self): return self._p


class FakeSession:
    """Vráti SAMPLE pre 26.9., inak prázdne — pre každú trasu."""
    def get(self, url, params=None, headers=None, timeout=None):
        return FakeResp(SAMPLE if params["outboundDepartureDateFrom"] == "2026-09-26" else EMPTY)


class FailingSession:
    def get(self, url, params=None, headers=None, timeout=None):
        raise RuntimeError("network down")


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def test_collect_once_all_destinations_and_directions():
    conn = make_conn()
    n = collect.collect_once(conn, "2026-06-30T14:00", destinations=DESTS,
                             origin="VIE", year=2026, month=9, session=FakeSession())
    # 2 destinacie x 2 smery x 1 let (26.9.) = 4
    assert n == 4
    rows = db.all_rows(conn)
    assert {r["destination"] for r in rows} == {"EFL", "ZTH"}
    assert {r["direction"] for r in rows} == {"OUT", "RET"}


def test_collect_once_atomic_on_failure():
    conn = make_conn()
    with pytest.raises(RuntimeError):
        collect.collect_once(conn, "2026-06-30T14:00", destinations=DESTS,
                             origin="VIE", year=2026, month=9, session=FailingSession())
    assert db.all_rows(conn) == []
