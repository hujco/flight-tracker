import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    direction TEXT NOT NULL,
    flight_date TEXT NOT NULL,
    flight_number TEXT NOT NULL,
    price REAL NOT NULL,
    seats_left INTEGER
);
CREATE INDEX IF NOT EXISTS idx_prices_lookup
    ON prices(direction, flight_date, observed_at);
"""


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def insert_observations(conn, observed_at, records):
    rows = [
        (
            observed_at,
            r["direction"],
            r["flight_date"],
            r["flight_number"],
            r["price"],
            r.get("seats_left"),
        )
        for r in records
    ]
    with conn:  # transakcia: vsetko alebo nic
        conn.executemany(
            "INSERT INTO prices "
            "(observed_at, direction, flight_date, flight_number, price, seats_left) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def all_rows(conn):
    cur = conn.execute("SELECT * FROM prices ORDER BY observed_at, id")
    return [dict(r) for r in cur.fetchall()]
