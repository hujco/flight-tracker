import sqlite3
from tracker import db


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def test_insert_and_read_back():
    conn = make_conn()
    records = [
        {"direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 34.99},
        {"direction": "RET", "flight_date": "2026-09-30", "flight_number": "FR7311", "price": 97.96, "seats_left": 5},
    ]
    n = db.insert_observations(conn, "2026-06-30T14:00", records)
    assert n == 2
    rows = db.all_rows(conn)
    assert len(rows) == 2
    assert rows[0]["observed_at"] == "2026-06-30T14:00"
    assert rows[0]["price"] == 34.99
    assert rows[0]["seats_left"] is None   # nezadane -> NULL
    assert rows[1]["seats_left"] == 5


def test_all_rows_sorted_by_observed_at():
    conn = make_conn()
    db.insert_observations(conn, "2026-06-30T15:00", [
        {"direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 40.0},
    ])
    db.insert_observations(conn, "2026-06-30T14:00", [
        {"direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 35.0},
    ])
    rows = db.all_rows(conn)
    assert [r["observed_at"] for r in rows] == ["2026-06-30T14:00", "2026-06-30T15:00"]


def test_connect_returns_row_factory_connection():
    conn = db.connect(":memory:")
    assert isinstance(conn, sqlite3.Connection)
    assert conn.row_factory is sqlite3.Row
