import sqlite3
from tracker import db


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def test_connect_returns_row_factory_connection():
    conn = db.connect(":memory:")
    assert isinstance(conn, sqlite3.Connection)
    assert conn.row_factory is sqlite3.Row


def test_insert_and_read_back_with_destination():
    conn = make_conn()
    records = [
        {"destination": "EFL", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 34.99},
        {"destination": "ZTH", "direction": "RET", "flight_date": "2026-09-30", "flight_number": "FR9", "price": 50.0, "seats_left": 3},
    ]
    n = db.insert_observations(conn, "2026-06-30T14:00", records)
    assert n == 2
    rows = db.all_rows(conn)
    assert rows[0]["destination"] == "EFL"
    assert rows[0]["seats_left"] is None
    assert rows[1]["destination"] == "ZTH"


def test_migration_backfills_old_rows_as_efl():
    # stary DB: tabulka bez stlpca destination + 1 riadok
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE prices (id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT, "
        "direction TEXT, flight_date TEXT, flight_number TEXT, price REAL, seats_left INTEGER);"
        "INSERT INTO prices (observed_at, direction, flight_date, flight_number, price) "
        "VALUES ('2026-06-30T10:00','OUT','2026-09-26','FR1',30.0);"
    )
    conn.commit()
    db.init_db(conn)  # migracia
    rows = db.all_rows(conn)
    assert rows[0]["destination"] == "EFL"   # stary riadok doplneny
    # novy insert s inou destinaciou funguje
    db.insert_observations(conn, "2026-06-30T11:00",
                           [{"destination": "PVK", "direction": "OUT", "flight_date": "2026-09-23", "flight_number": "FR2", "price": 35.0}])
    dests = {r["destination"] for r in db.all_rows(conn)}
    assert dests == {"EFL", "PVK"}
