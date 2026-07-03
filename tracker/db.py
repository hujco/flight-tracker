import sqlite3

_CREATE = """
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    destination TEXT,
    direction TEXT NOT NULL,
    flight_date TEXT NOT NULL,
    flight_number TEXT NOT NULL,
    price REAL NOT NULL,
    seats_left INTEGER
);
"""
_INDEX = ("CREATE INDEX IF NOT EXISTS idx_prices_lookup "
          "ON prices(destination, direction, flight_date, observed_at);")


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn):
    return {r[1] for r in conn.execute("PRAGMA table_info(prices)").fetchall()}


def init_db(conn):
    conn.execute(_CREATE)
    if "destination" not in _columns(conn):   # migracia stareho DB
        conn.execute("ALTER TABLE prices ADD COLUMN destination TEXT")
        conn.execute("UPDATE prices SET destination='EFL' WHERE destination IS NULL")
    conn.execute(_INDEX)
    conn.commit()


def insert_observations(conn, observed_at, records):
    rows = [
        (
            observed_at,
            r["destination"],
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
            "(observed_at, destination, direction, flight_date, flight_number, price, seats_left) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def all_rows(conn):
    cur = conn.execute("SELECT * FROM prices ORDER BY observed_at, id")
    return [dict(r) for r in cur.fetchall()]
