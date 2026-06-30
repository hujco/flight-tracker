# Multi-destination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rozšíriť tracker z jednej destinácie (EFL) na tri (EFL, PVK, ZTH) — VIE↔ostrov, s prepínačom destinácií v reporte a Telegram alertom per destinácia.

**Architecture:** Pridať stĺpec `destination` do `prices` (idempotentná migrácia starých dát na EFL). Zber iteruje destinácie × smery. Round-trip a alert sa robia per destinácia tým, že volajúci (report/notify) najprv odfiltrujú riadky na jednu destináciu a potom volajú **nezmenené** `stats.py`. Report má dvojúrovňový prepínač (destinácia × 7/9/10 nocí).

**Tech Stack:** Python 3.9 (venv `.venv`), requests, sqlite3, plotly, pytest.

## Global Constraints

- Python 3.9; deps vo venv `.venv`; testy cez `.venv/bin/python -m pytest`.
- Origin VIE; destinácie EFL (Kefalonia), PVK (Lefkada/Preveza), ZTH (Zakyntos).
- `direction`: OUT = VIE→destinácia, RET = destinácia→VIE. Round-trip sa páruje len v rámci tej istej destinácie.
- Referencia (~117 €/os, 301 €/2 os.) aj alert cieľ (130 €/os) sú globálne pre všetky destinácie.
- `stats.py` sa NEMENÍ — destinácia sa rieši filtrovaním riadkov pred volaním.
- Atomicita zberu: zozbierať všetky záznamy, potom jeden transakčný insert.
- Migrácia `destination` je idempotentná (beží pri každom `init_db`, aj v CI nad commitnutou `prices.db`).
- `seats_left` ostáva NULL. Dátumy EU formát DD.MM.YYYY. Commit po každej úlohe.

## File Structure

- `tracker/config.py` — pridať `ORIGIN`, `DESTINATIONS`; odstrániť nepoužívané `LEGS`.
- `tracker/db.py` — schéma + migrácia `destination`, insert/all_rows s destináciou.
- `tracker/fetch.py` — `parse_fares`/`fetch_leg` značia destináciu.
- `tracker/collect.py` — iterovať `DESTINATIONS` × {OUT,RET}.
- `tracker/notify.py` — `maybe_notify` per destinácia; `format_message` s názvom ostrova.
- `tracker/report.py` — prepínač destinácií okolo existujúceho prepínača nocí.
- `tracker/run.py` — bez zmeny (overí sa v poslednej úlohe).
- testy: `tests/test_db.py`, `test_fetch.py`, `test_collect.py`, `test_notify.py`, `test_report.py`.

---

### Task 1: Config destinácií + DB stĺpec `destination` s migráciou

**Files:**
- Modify: `tracker/config.py`
- Modify: `tracker/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nič nové.
- Produces:
  - `config.ORIGIN = "VIE"`; `config.DESTINATIONS = [{"code","label"}, ...]` (EFL/PVK/ZTH).
  - `db.init_db(conn)` vytvorí tabuľku s `destination TEXT`, a ak chýba (starý DB), pridá ho a doplní existujúce riadky na `'EFL'`.
  - `db.insert_observations(conn, observed_at, records)` — record má kľúč `destination`.
  - `db.all_rows` vracia aj `destination`.

- [ ] **Step 1: Uprav `tracker/config.py`** — nahraď blok `LEGS = [...]` týmto:

```python
# OUT = tam (VIE->destinacia), RET = spat (destinacia->VIE)
ORIGIN = "VIE"
DESTINATIONS = [
    {"code": "EFL", "label": "Kefalonia"},
    {"code": "PVK", "label": "Lefkada"},    # letisko Preveza/Aktion
    {"code": "ZTH", "label": "Zakyntos"},
]
```

- [ ] **Step 2: Napíš padajúce testy `tests/test_db.py`** — nahraď celý obsah súboru:

```python
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
```

- [ ] **Step 3: Spusti — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_db.py -v`
Expected: FAIL (KeyError 'destination' / no such column destination).

- [ ] **Step 4: Implementuj `tracker/db.py`** — nahraď celý obsah súboru:

```python
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
```

- [ ] **Step 5: Spusti — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_db.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/config.py tracker/db.py tests/test_db.py
git commit -m "feat: add destination column + idempotent migration; config DESTINATIONS"
```

---

### Task 2: Fetch značí destináciu

**Files:**
- Modify: `tracker/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: nič z iných modulov.
- Produces:
  - `fetch.parse_fares(payload, direction, destination) -> list[dict]` — záznam má kľúče `destination, direction, flight_date, flight_number, price, seats_left`.
  - `fetch.fetch_leg(origin, arrival, direction, destination, year, month, session=None, currency="EUR") -> list[dict]` — `origin`/`arrival` sú IATA pre dotaz, `destination` je značka uložená do záznamov.
  - `fetch.fetch_day`, `fetch.days_in_month` — bez zmeny.

- [ ] **Step 1: Napíš padajúce testy `tests/test_fetch.py`** — nahraď celý obsah:

```python
from tracker import fetch

SAMPLE = {
    "fares": [
        {"outbound": {"departureDate": "2026-09-26T11:55:00",
                      "price": {"value": 34.99}, "flightNumber": "FR7310"}}
    ]
}
EMPTY = {"fares": []}


def test_parse_fares_tags_destination():
    recs = fetch.parse_fares(SAMPLE, "OUT", "EFL")
    assert recs == [{
        "destination": "EFL", "direction": "OUT", "flight_date": "2026-09-26",
        "flight_number": "FR7310", "price": 34.99, "seats_left": None,
    }]


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


def test_fetch_leg_tags_destination_and_iterates():
    sess = FakeSession({"2026-09-26": SAMPLE})
    recs = fetch.fetch_leg("VIE", "PVK", "OUT", "PVK", 2026, 9, session=sess)
    assert len(sess.calls) == 30
    assert len(recs) == 1
    assert recs[0]["destination"] == "PVK"
    assert sess.calls[0]["departureAirportIataCode"] == "VIE"
    assert sess.calls[0]["arrivalAirportIataCode"] == "PVK"
```

- [ ] **Step 2: Spusti — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_fetch.py -v`
Expected: FAIL (parse_fares takes 2 args / missing destination).

- [ ] **Step 3: Implementuj zmeny v `tracker/fetch.py`** — nahraď funkcie `parse_fares` a `fetch_leg` (ostatné nechaj):

```python
def parse_fares(payload, direction, destination):
    records = []
    for fare in payload.get("fares", []):
        ob = fare["outbound"]
        records.append(
            {
                "destination": destination,
                "direction": direction,
                "flight_date": ob["departureDate"][:10],
                "flight_number": ob["flightNumber"],
                "price": ob["price"]["value"],
                "seats_left": None,
            }
        )
    return records


def fetch_leg(origin, arrival, direction, destination, year, month,
              session=None, currency="EUR"):
    records = []
    for day in days_in_month(year, month):
        payload = fetch_day(origin, arrival, day, session=session, currency=currency)
        records.extend(parse_fares(payload, direction, destination))
    return records
```

- [ ] **Step 4: Spusti — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_fetch.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/fetch.py tests/test_fetch.py
git commit -m "feat: fetch tags destination on records"
```

---

### Task 3: Collect iteruje destinácie

**Files:**
- Modify: `tracker/collect.py`
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: `config.DESTINATIONS/ORIGIN/YEAR/MONTH/CURRENCY`, `fetch.fetch_leg(origin, arrival, direction, destination, year, month, session=, currency=)`, `db.insert_observations`.
- Produces:
  - `collect.collect_once(conn, observed_at, destinations=None, origin=None, year=None, month=None, currency=None, session=None) -> int` — pre každú destináciu zozbiera OUT (origin→code) aj RET (code→origin), tagne destination, urobí JEDEN insert; pri zlyhaní ktorejkoľvek nohy nič nezapíše.

- [ ] **Step 1: Napíš padajúce testy `tests/test_collect.py`** — nahraď celý obsah:

```python
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
```

- [ ] **Step 2: Spusti — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_collect.py -v`
Expected: FAIL (collect_once nepozná `destinations`/`origin`).

- [ ] **Step 3: Implementuj `tracker/collect.py`** — nahraď celý obsah:

```python
from . import config, db, fetch


def collect_once(conn, observed_at, destinations=None, origin=None,
                 year=None, month=None, currency=None, session=None):
    destinations = destinations if destinations is not None else config.DESTINATIONS
    origin = origin if origin is not None else config.ORIGIN
    year = year if year is not None else config.YEAR
    month = month if month is not None else config.MONTH
    currency = currency if currency is not None else config.CURRENCY

    records = []
    for dst in destinations:
        code = dst["code"]
        records.extend(fetch.fetch_leg(
            origin, code, "OUT", code, year, month, session=session, currency=currency))
        records.extend(fetch.fetch_leg(
            code, origin, "RET", code, year, month, session=session, currency=currency))
    # vsetky volania presli -> az teraz jeden transakcny insert
    return db.insert_observations(conn, observed_at, records)
```

- [ ] **Step 4: Spusti — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_collect.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/collect.py tests/test_collect.py
git commit -m "feat: collect iterates destinations x directions"
```

---

### Task 4: Alert per destinácia

**Files:**
- Modify: `tracker/notify.py`
- Test: `tests/test_notify.py`

**Interfaces:**
- Consumes: `config.DESTINATIONS/STAY_PRESETS/ALERT_TARGET_EUR/REFERENCE_PER_PERSON_EUR/REPORT_URL/TELEGRAM_CHAT_ID`, `stats.cheapest_roundtrip_now`.
- Produces:
  - `notify.format_message(info, destination_label, reference_per_person, target, report_url)` — text obsahuje názov ostrova.
  - `notify.maybe_notify(rows, session=None) -> (bool, str)` — prejde každú destináciu z `config.DESTINATIONS`, odfiltruje riadky na ňu, zistí nové minimum pod cieľom a pošle Telegram (správa menuje ostrov); viac destinácií = viac správ.
  - `detect_new_low`, `cheapest_per_observation`, `send_telegram`, `send_test` — bez zmeny.

- [ ] **Step 1: Nahraď v `tests/test_notify.py` test pre `format_message` a pridaj test pre `maybe_notify`.** Najprv uprav oba existujúce `test_format_message_*` (pridaj argument `destination_label`) a doplň nový test. Konkrétne nahraď obe funkcie `test_format_message_tiers_great_when_below_reference` a `test_format_message_good_when_above_reference` týmto:

```python
def test_format_message_includes_destination_and_tier():
    info = {"price": 110.0, "observed_at": "t1", "prev_low": 130.0,
            "combo": {"out_date": "2026-09-07", "ret_date": "2026-09-14", "nights": 7, "label": "7 nocí"}}
    msg = notify.format_message(info, "Lefkada", reference_per_person=117.0, target=130.0, report_url="http://x")
    assert "Lefkada" in msg
    assert "Skvelá" in msg               # 110 <= 117
    assert "07.09.2026" in msg and "110 €/os" in msg

    msg2 = notify.format_message({**info, "price": 125.0}, "Zakyntos", 117.0, 130.0, "http://x")
    assert "Zakyntos" in msg2 and "Dobrá cena" in msg2   # 125 > 117
```

A pridaj na koniec súboru:

```python
def _row(ts, dest, direction, fdate, price):
    return {"observed_at": ts, "destination": dest, "direction": direction,
            "flight_date": fdate, "flight_number": "FR", "price": price}


def test_maybe_notify_per_destination(monkeypatch):
    # EFL klesne na nove minimum pod cielom, ZTH ostava draha
    rows = [
        _row("t1", "EFL", "OUT", "2026-09-07", 70.0), _row("t1", "EFL", "RET", "2026-09-14", 70.0),  # 140
        _row("t2", "EFL", "OUT", "2026-09-07", 50.0), _row("t2", "EFL", "RET", "2026-09-14", 55.0),  # 105 (nove min < 130)
        _row("t2", "ZTH", "OUT", "2026-09-07", 100.0), _row("t2", "ZTH", "RET", "2026-09-14", 100.0),  # 200
    ]
    sent = []

    class S:
        def post(self, url, data=None, timeout=None):
            sent.append(data["text"])
            class R:
                def raise_for_status(self_): pass
                def json(self_): return {"ok": True}
            return R()

    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    ok, msg = notify.maybe_notify(rows, session=S())
    assert ok is True
    assert len(sent) == 1                 # len EFL
    assert "Kefalonia" in sent[0]
```

- [ ] **Step 2: Spusti — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_notify.py -v`
Expected: FAIL (`format_message` berie iný počet argumentov; `maybe_notify` nerieši destinácie).

- [ ] **Step 3: Implementuj zmeny v `tracker/notify.py`.** Nahraď funkciu `format_message` (pridaj `destination_label`) a funkciu `maybe_notify`:

```python
def format_message(info, destination_label, reference_per_person, target, report_url):
    c = info["combo"]
    price = info["price"]
    if price <= reference_per_person:
        head = "🔥 Skvelá cena (ako pred 2 rokmi!)"
    else:
        head = "✅ Dobrá cena"
    lines = [
        f"<b>{head} — {destination_label}</b>",
        f"Letenka VIE↔{destination_label}: <b>{price:.0f} €/os</b> ({c['label']})",
        f"{_fmt_date(c['out_date'])} → {_fmt_date(c['ret_date'])} · {c['nights']} nocí",
    ]
    if info["prev_low"] is not None:
        lines.append(f"Predošlé minimum: {info['prev_low']:.0f} €/os")
    lines.append(f"Cieľ: ≤ {target:.0f} €/os")
    lines.append(report_url)
    return "\n".join(lines)


def maybe_notify(rows, session=None):
    """Pre každú destináciu zisti nové minimum pod cieľom a pošli Telegram."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.TELEGRAM_CHAT_ID
    msgs = []
    sent_any = False
    for dst in config.DESTINATIONS:
        drows = [r for r in rows if r.get("destination") == dst["code"]]
        info = detect_new_low(drows, config.STAY_PRESETS, config.ALERT_TARGET_EUR)
        if info is None:
            continue
        if not token or not chat_id:
            msgs.append(f"{dst['label']}: nové min {info['price']:.0f} €, ale chýba TELEGRAM_TOKEN")
            continue
        text = format_message(info, dst["label"], config.REFERENCE_PER_PERSON_EUR,
                              config.ALERT_TARGET_EUR, config.REPORT_URL)
        send_telegram(token, chat_id, text, session=session)
        sent_any = True
        msgs.append(f"{dst['label']}: poslaný alert {info['price']:.0f} €/os")
    if not msgs:
        return False, "žiadne nové minimum pod cieľom"
    return sent_any, "; ".join(msgs)
```

- [ ] **Step 4: Spusti — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_notify.py -v`
Expected: PASS (všetky testy v súbore).

- [ ] **Step 5: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/notify.py tests/test_notify.py
git commit -m "feat: per-destination Telegram alerts naming the island"
```

---

### Task 5: Report — prepínač destinácií

**Files:**
- Modify: `tracker/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `config.DESTINATIONS/STAY_PRESETS/...`, `stats.*` (na riadkoch odfiltrovaných per destinácia), existujúce `_preset_block`, `_price_evolution_fig`, `_chart_html`, `_kpi_cards_html`, `_combos_table_html`, `_fmt_dt`.
- Produces:
  - `report.build_report_html(rows)` — má hore prepínač destinácií; pre každú destináciu vlastný panel s existujúcim prepínačom 7/9/10 nocí, KPI, tabuľkou a oboma grafmi. Prázdne `rows` → „Zatiaľ žiadne dáta".

- [ ] **Step 1: Napíš/aktualizuj `tests/test_report.py`** — nahraď celý obsah:

```python
from tracker import report

ROWS = [
    {"observed_at": "2026-06-30T14:00", "destination": "EFL", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR1", "price": 35.0},
    {"observed_at": "2026-06-30T14:00", "destination": "EFL", "direction": "RET", "flight_date": "2026-10-03", "flight_number": "FR2", "price": 98.0},  # 7 noci
    {"observed_at": "2026-06-30T14:00", "destination": "ZTH", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR3", "price": 30.0},
    {"observed_at": "2026-06-30T14:00", "destination": "ZTH", "direction": "RET", "flight_date": "2026-10-03", "flight_number": "FR4", "price": 60.0},  # 7 noci
]


def test_report_has_destination_toggle():
    html = report.build_report_html(ROWS)
    assert "<html" in html.lower()
    assert "Kefalonia" in html and "Lefkada" in html and "Zakyntos" in html
    assert html.count("dest-btn") >= 3        # tlacidlo na kazdu destinaciu
    assert "133" in html                       # EFL 35+98 v tabulke (7 noci)
    assert "Najlacnejší round-trip" in html


def test_report_empty():
    assert "Zatiaľ žiadne dáta" in report.build_report_html([])


def test_write_report_creates_file(tmp_path):
    out = tmp_path / "report.html"
    report.write_report(ROWS, out)
    assert out.exists() and "Kefalonia" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Spusti — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_report.py -v`
Expected: FAIL (žiadny `dest-btn` / chýbajú destinácie).

- [ ] **Step 3: Uprav `tracker/report.py`.** (a) Nahraď `_TOGGLE_JS` rozšírenou verziou (prepínač destinácií + scoped prepínač nocí):

```python
_TOGGLE_JS = """<script>
(function () {
  function resizeVisible() {
    if (!window.Plotly) return;
    document.querySelectorAll(".dest-panel:not([hidden]) .plotly-graph-div")
      .forEach(function (g) {
        if (!g.closest("[hidden]")) window.Plotly.Plots.resize(g);
      });
  }
  document.querySelectorAll(".dest-btn").forEach(function (b) {
    b.addEventListener("click", function () {
      var d = b.dataset.dest;
      document.querySelectorAll(".dest-btn").forEach(function (x) {
        x.classList.toggle("active", x.dataset.dest === d); });
      document.querySelectorAll(".dest-panel").forEach(function (p) {
        p.hidden = (p.dataset.dest !== d); });
      resizeVisible();
    });
  });
  document.querySelectorAll(".toggle-btn").forEach(function (b) {
    b.addEventListener("click", function () {
      var panel = b.closest(".dest-panel");
      var t = b.dataset.target;
      panel.querySelectorAll(".toggle-btn").forEach(function (x) {
        x.classList.toggle("active", x.dataset.target === t); });
      panel.querySelectorAll(".preset").forEach(function (p) {
        p.hidden = (p.dataset.preset !== t); });
      resizeVisible();
    });
  });
})();
</script>"""
```

(b) Pridaj novú funkciu `_dest_panel` (nad `build_report_html`):

```python
def _dest_panel(rows, dest, index):
    """Panel jednej destinácie: prepínač nocí + presety + graf vývoja."""
    buttons = "".join(
        f"<button class='toggle-btn{' active' if i == 0 else ''}' data-target='{i}'>"
        f"{html.escape(p['label'])}</button>"
        for i, p in enumerate(config.STAY_PRESETS)
    )
    toggle = (f"<div class='toggle-wrap'><span class='toggle-label'>Dĺžka pobytu:</span> "
              f"<div class='toggle' role='tablist'>{buttons}</div></div>")
    blocks = "".join(_preset_block(rows, p, i) for i, p in enumerate(config.STAY_PRESETS))
    evolution = _chart_html(_price_evolution_fig(rows))
    hidden = "" if index == 0 else " hidden"
    return f"""<div class='dest-panel' data-dest='{html.escape(dest['code'])}'{hidden}>
  {toggle}
  {blocks}
  <section class='evolution'>
    <h2>Vývoj ceny v čase</h2>
    <p class='caption'>Najnižšia cena odletu a návratu (za 1 os.) pri každom meraní — nezávislé od dĺžky pobytu.</p>
    {evolution}
  </section>
</div>"""
```

(c) Nahraď telo `build_report_html` (časť s dátami, NIE prázdny návrat) tak, aby stavalo prepínač destinácií a panely. Nahraď blok od `updated = ...` po koniec `return f"""..."""`:

```python
    updated = stats.latest_observed_at(rows)
    dest_buttons = "".join(
        f"<button class='dest-btn{' active' if i == 0 else ''}' data-dest='{html.escape(d['code'])}'>"
        f"{html.escape(d['label'])}</button>"
        for i, d in enumerate(config.DESTINATIONS)
    )
    panels = "".join(
        _dest_panel([r for r in rows if r.get("destination") == d["code"]], d, i)
        for i, d in enumerate(config.DESTINATIONS)
    )

    return f"""<!DOCTYPE html>
<html lang='sk'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Ryanair VIE tracker</title>
{_PLOTLY_JS}
<style>{_CSS}</style>
</head>
<body>
<div class='wrap'>
  <header>
    <div class='eyebrow'>Ryanair price tracker · september 2026</div>
    <h1>Viedeň → grécke ostrovy</h1>
    <div class='updated'>Posledná aktualizácia: {html.escape(_fmt_dt(updated))}</div>
  </header>
  <div class='toggle-wrap'><span class='toggle-label'>Destinácia:</span>
    <div class='toggle' role='tablist'>{dest_buttons}</div></div>
  {panels}
  <footer>Dáta: services-api.ryanair.com · generované lokálne, bez LLM</footer>
</div>
{_TOGGLE_JS}
</body>
</html>"""
```

(d) Pridaj CSS pre `.dest-btn` — vlož do `_CSS` hneď za pravidlo `.toggle-btn.active { ... }`:

```python
.dest-btn { cursor: pointer; border: 0; background: transparent; color: #94A3B8;
  font: 600 14px 'Fira Sans', sans-serif; padding: 8px 16px; border-radius: 9px;
  transition: background .2s, color .2s; }
.dest-btn.active { background: #F59E0B; color: #0B1120; }
.dest-btn:hover:not(.active) { color: #E2E8F0; }
```

- [ ] **Step 4: Spusti — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_report.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/report.py tests/test_report.py
git commit -m "feat: report destination toggle around stay-length toggle"
```

---

### Task 6: Integrácia — ostrý beh, migrácia reálnej DB, README

**Files:**
- Modify: `README.md`
- (overiť: `tracker/run.py` bez zmeny)

**Interfaces:**
- Consumes: celý balík.
- Produces: overený end-to-end beh so 3 destináciami; aktualizovaný README.

- [ ] **Step 1: Spusti celú sadu testov**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest -v`
Expected: PASS (všetky súbory zelené).

- [ ] **Step 2: Ostrý beh proti živému API (migruje reálnu `prices.db` a zozbiera 3 destinácie)**

Run:
```bash
cd ~/www/flight-tracker
.venv/bin/python -m tracker.run
.venv/bin/python -c "
import sqlite3
c = sqlite3.connect('prices.db')
print('destinacie v DB:', sorted({r[0] for r in c.execute('select destination from prices')}))
print('riadkov:', c.execute('select count(*) from prices').fetchone()[0])
"
```
Expected: `destinacie v DB: ['EFL', 'PVK', 'ZTH']` (staré EFL dáta zachované + migrované, nové PVK/ZTH pribudli); log „collected N rows". Otvor `report.html` a over, že hore je prepínač destinácií a funguje aj prepínač nocí v každej.

- [ ] **Step 3: Aktualizuj `README.md`** — nahraď prvý odsek (popis) a sekciu „Konfigurácia":

Prvý odsek pod nadpisom nahraď za:
```markdown
Sleduje každú hodinu ceny letov Ryanair z Viedne na grécke ostrovy
**Kefalonia (EFL), Lefkada (PVK), Zakyntos (ZTH)** za september 2026,
ukladá históriu do SQLite a generuje `report.html` s grafmi a prepínačom
destinácií. Bez LLM.
```

Sekciu „## Konfigurácia" nahraď za:
```markdown
## Konfigurácia
Destinácie a okno v `tracker/config.py` (`ORIGIN`, `DESTINATIONS`, `YEAR`, `MONTH`,
`STAY_PRESETS`, `PERSONS`, `EXTRAS_EUR`, `INCLUDE_EXTRAS`, `REFERENCE_PRICE_EUR`,
`ALERT_TARGET_EUR`). Pridanie destinácie = jeden záznam `{code, label}` v `DESTINATIONS`.
```

- [ ] **Step 4: Commit**

```bash
cd ~/www/flight-tracker
git add README.md
git commit -m "docs: README for multi-destination tracking"
```

---

## Self-Review

**1. Spec coverage:**
- `destination` stĺpec + migrácia EFL → Task 1. ✓
- Config ORIGIN/DESTINATIONS → Task 1. ✓
- Zber destinácie × smery, atomicita → Task 3 (fetch tag Task 2). ✓
- stats.py nezmenené, filter per destinácia → použité v Task 4 (notify) a Task 5 (report). ✓
- Report dvojúrovňový prepínač → Task 5. ✓
- Alert per destinácia, správa menuje ostrov → Task 4. ✓
- Globálna referencia/cieľ → použité v notify/report bez per-dest hodnôt. ✓
- Migrácia beží v CI nad reálnou DB → overené v Task 6 Step 2. ✓
- EU dátumy, seats NULL, atomicita → zachované (Task 1/2/3). ✓

**2. Placeholder scan:** žiadne TBD; každý krok má reálny kód a príkazy. ✓

**3. Type consistency:** record kľúče `destination/direction/flight_date/flight_number/price/seats_left` konzistentné (db/fetch/collect). `fetch_leg(origin, arrival, direction, destination, year, month, ...)` volané rovnako v collect. `format_message(info, destination_label, reference_per_person, target, report_url)` konzistentné medzi notify a testom. `_preset_block`/`_price_evolution_fig`/`_chart_html` použité v `_dest_panel` existujú v report.py. ✓
