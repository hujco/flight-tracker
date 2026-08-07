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


def _cols(conn):
    return {r[1] for r in conn.execute("PRAGMA table_info(prices)")}


def test_migration_adds_new_columns_to_old_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE prices (id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT, "
        "direction TEXT, flight_date TEXT, flight_number TEXT, price REAL, seats_left INTEGER);"
        "INSERT INTO prices (observed_at, direction, flight_date, flight_number, price) "
        "VALUES ('2026-06-30T10:00','OUT','2026-09-26','FR1',30.0);"
    )
    conn.commit()
    db.init_db(conn)
    assert {"departure_time", "arrival_time", "currency",
            "price_updated", "previous_price"} <= _cols(conn)
    assert db.all_rows(conn)[0]["price_updated"] is None   # stary riadok ostane NULL


def test_init_db_replaces_stale_index_without_origin():
    # povodny idx_prices_lookup vznikol pred multi-origin a IF NOT EXISTS ho
    # nikdy nenahradil -> filtre podla origin/destination isli mimo indexu
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE prices (id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT, "
        "origin TEXT, destination TEXT, direction TEXT, flight_date TEXT, "
        "flight_number TEXT, price REAL, seats_left INTEGER);"
        "CREATE INDEX idx_prices_lookup ON prices(direction, flight_date, observed_at);"
    )
    conn.commit()
    db.init_db(conn)
    idx = {r[0]: r[1] for r in
           conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' "
                        "AND name LIKE 'idx%'")}
    assert "idx_prices_lookup" not in idx
    assert "origin" in idx["idx_prices_lookup_v2"]


def test_insert_stores_price_updated_and_times():
    conn = make_conn()
    db.insert_observations(conn, "2026-08-06T06:00", [{
        "origin": "BUD", "destination": "PVK", "direction": "OUT",
        "flight_date": "2026-09-06", "flight_number": "FR7770", "price": 49.99,
        "departure_time": "2026-09-06T05:50:00", "arrival_time": "2026-09-06T08:40:00",
        "currency": "EUR", "price_updated": "2026-08-06T06:26:36+00:00",
        "previous_price": 45.0,
    }])
    r = db.all_rows(conn)[0]
    assert r["departure_time"] == "2026-09-06T05:50:00"
    assert r["price_updated"] == "2026-08-06T06:26:36+00:00"
    assert r["previous_price"] == 45.0 and r["currency"] == "EUR"


def test_alerts_roundtrip_for_cooldown():
    conn = make_conn()
    assert db.last_alert(conn, "spike") is None
    db.record_alert(conn, "2026-08-06T06:00", "spike", 198.0, "2026-08-06T05:41")
    db.record_alert(conn, "2026-08-07T06:00", "spike", 201.0, "2026-08-07T05:41")
    last = db.last_alert(conn, "spike")
    assert last["sent_at"] == "2026-08-07T06:00" and last["price"] == 201.0
    assert db.last_alert(conn, "target") is None   # druhy druh sa nemieša
