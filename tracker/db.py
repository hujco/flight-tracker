import sqlite3

_CREATE = """
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    origin TEXT,
    destination TEXT,
    direction TEXT NOT NULL,
    flight_date TEXT NOT NULL,
    flight_number TEXT NOT NULL,
    price REAL NOT NULL,
    seats_left INTEGER
);
"""
# v2: pôvodný idx_prices_lookup vznikol pred multi-origin a neobsahoval origin ani
# destination. CREATE INDEX IF NOT EXISTS ho nikdy nenahradil, preto nové meno.
_INDEX = ("CREATE INDEX IF NOT EXISTS idx_prices_lookup_v2 "
          "ON prices(origin, destination, direction, flight_date, observed_at);")
_DROP_OLD_INDEX = "DROP INDEX IF EXISTS idx_prices_lookup;"

_CREATE_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    price REAL,
    observed_at TEXT
);
"""

# Stĺpce doplnené neskôr; migrácia je „pridaj ak chýba" (staré riadky ostanú NULL).
_ADDED_COLUMNS = {
    "departure_time": "TEXT",
    "arrival_time": "TEXT",
    "currency": "TEXT",
    "price_updated": "TEXT",
    "previous_price": "REAL",
}

_INSERT_COLUMNS = ("observed_at", "origin", "destination", "direction", "flight_date",
                   "flight_number", "price", "seats_left", "departure_time",
                   "arrival_time", "currency", "price_updated", "previous_price")


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn):
    return {r[1] for r in conn.execute("PRAGMA table_info(prices)").fetchall()}


def init_db(conn):
    conn.execute(_CREATE)
    cols = _columns(conn)
    if "destination" not in cols:   # migracia stareho DB (pred multi-destinacie)
        conn.execute("ALTER TABLE prices ADD COLUMN destination TEXT")
        conn.execute("UPDATE prices SET destination='EFL' WHERE destination IS NULL")
    if "origin" not in cols:        # migracia stareho DB (pred multi-origin): vsetko bolo VIE
        conn.execute("ALTER TABLE prices ADD COLUMN origin TEXT")
        conn.execute("UPDATE prices SET origin='VIE' WHERE origin IS NULL")
    for name, sql_type in _ADDED_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE prices ADD COLUMN {name} {sql_type}")
    conn.execute(_DROP_OLD_INDEX)
    conn.execute(_INDEX)
    conn.execute(_CREATE_ALERTS)
    conn.commit()


def insert_observations(conn, observed_at, records):
    rows = [
        (
            observed_at,
            r.get("origin"),
            r["destination"],
            r["direction"],
            r["flight_date"],
            r["flight_number"],
            r["price"],
            r.get("seats_left"),
            r.get("departure_time"),
            r.get("arrival_time"),
            r.get("currency"),
            r.get("price_updated"),
            r.get("previous_price"),
        )
        for r in records
    ]
    placeholders = ", ".join("?" * len(_INSERT_COLUMNS))
    with conn:  # transakcia: vsetko alebo nic
        conn.executemany(
            f"INSERT INTO prices ({', '.join(_INSERT_COLUMNS)}) VALUES ({placeholders})",
            rows,
        )
    return len(rows)


def record_alert(conn, sent_at, kind, price, observed_at):
    with conn:
        conn.execute(
            "INSERT INTO alerts (sent_at, kind, price, observed_at) VALUES (?, ?, ?, ?)",
            (sent_at, kind, price, observed_at),
        )


def last_alert_any(conn):
    """Posledný odoslaný alert akéhokoľvek druhu (na heartbeat), alebo None."""
    cur = conn.execute("SELECT * FROM alerts ORDER BY sent_at DESC LIMIT 1")
    row = cur.fetchone()
    return dict(row) if row else None


def last_alert(conn, kind):
    """Posledný odoslaný alert daného druhu (na cooldown), alebo None."""
    cur = conn.execute(
        "SELECT * FROM alerts WHERE kind = ? ORDER BY sent_at DESC LIMIT 1", (kind,))
    row = cur.fetchone()
    return dict(row) if row else None


def all_rows(conn):
    cur = conn.execute("SELECT * FROM prices ORDER BY observed_at, id")
    return [dict(r) for r in cur.fetchall()]
