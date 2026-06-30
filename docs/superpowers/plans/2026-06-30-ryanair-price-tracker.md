# Ryanair Price Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Každú hodinu zbierať ceny letov Ryanair VIE↔EFL za september 2026, ukladať históriu do SQLite a generovať HTML grafy.

**Architecture:** Dva čisté Python moduly komunikujúce cez SQLite súbor — `fetch`/`collect` (zber z `farfnd` endpointu deň po dni) a `stats`/`report` (výpočty + Plotly HTML). Spúšťa ich hodinový `launchd` agent cez tenký runner `tracker/run.py`. Žiadne LLM.

**Tech Stack:** Python 3.9+, `requests` (HTTP), `sqlite3` (stdlib), `plotly` (grafy), `pytest` (testy), `launchd` (scheduler na macOS).

## Global Constraints

- Python 3.9+ (systém má 3.9.6; kód nepoužíva nič novšie — `defaultdict`, `pathlib`, `isoformat(timespec=)`, f-stringy).
- Závislosti sa inštalujú do venv `.venv` v koreni projektu (Apple `/usr/bin/python3` nedovolí priamy `pip install`).
- Žiadny API kľúč, žiadna session — len verejný endpoint `https://services-api.ryanair.com/farfnd/v4/oneWayFares`.
- HTTP hlavička `User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)` pri každom requeste.
- Sekvenčné volania (žiadny paralelizmus), timeout 20 s na request.
- Trasa a okno z `tracker/config.py`: LEGS = OUT(VIE→EFL), RET(EFL→VIE); YEAR=2026, MONTH=9, CURRENCY="EUR".
- `seats_left` je vždy `None` (endpoint ho nevracia) — stĺpec ostáva v schéme.
- Pri akomkoľvek zlyhaní zberu sa NIČ nezapíše (atomicita): najprv sa zozbierajú všetky záznamy, až potom jeden transakčný insert.
- Projekt žije v `~/www/flight-tracker`. Balík kódu je `tracker/`, testy v `tests/`.
- Commit po každej úlohe.

## File Structure

- `tracker/__init__.py` — označí balík.
- `tracker/config.py` — konštanty (trasa, okno, cesty k súborom).
- `tracker/db.py` — SQLite schéma + insert/query helpery.
- `tracker/fetch.py` — Ryanair klient + parsovanie JSON.
- `tracker/collect.py` — orchestrácia: zber všetkých nôh → jeden insert.
- `tracker/stats.py` — čisté funkcie nad riadkami (série, najlacnejší round-trip).
- `tracker/report.py` — render `report.html` z Plotly grafov + tabuľky.
- `tracker/run.py` — runner: collect → report, logovanie, skip-on-error.
- `tests/test_db.py`, `tests/test_fetch.py`, `tests/test_stats.py`, `tests/test_report.py`.
- `requirements.txt`, `README.md`.
- `com.flighttracker.hourly.plist` — launchd agent.

---

### Task 1: Projektový skelet, config a DB vrstva

**Files:**
- Create: `requirements.txt`
- Create: `tracker/__init__.py`
- Create: `tracker/config.py`
- Create: `tracker/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nič (prvá úloha).
- Produces:
  - `config.LEGS: list[dict]` s kľúčmi `direction`, `origin`, `destination`; `config.YEAR:int`, `config.MONTH:int`, `config.CURRENCY:str`; `config.DB_PATH`, `config.REPORT_PATH`, `config.LOG_PATH` (`pathlib.Path`).
  - `db.connect(db_path) -> sqlite3.Connection` (s `row_factory=sqlite3.Row`).
  - `db.init_db(conn) -> None`.
  - `db.insert_observations(conn, observed_at: str, records: list[dict]) -> int` — record má kľúče `direction, flight_date, flight_number, price` a voliteľne `seats_left`.
  - `db.all_rows(conn) -> list[dict]` zoradené podľa `observed_at`.

- [ ] **Step 1: Vytvor `requirements.txt` a venv**

Vytvor `requirements.txt`:
```text
requests==2.32.3
plotly==5.24.1
pytest==8.3.3
```

Potom vytvor venv a nainštaluj (Apple `/usr/bin/python3` nedovolí priamy `pip install`):
```bash
cd ~/www/flight-tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Všetky testové príkazy v tomto pláne používajú `.venv/bin/python -m pytest`.

- [ ] **Step 2: Vytvor `tracker/__init__.py`** (prázdny súbor)

```python
```

- [ ] **Step 3: Vytvor `tracker/config.py`**

```python
from pathlib import Path

YEAR = 2026
MONTH = 9
CURRENCY = "EUR"

# OUT = tam (VIE->EFL), RET = spat (EFL->VIE)
LEGS = [
    {"direction": "OUT", "origin": "VIE", "destination": "EFL"},
    {"direction": "RET", "origin": "EFL", "destination": "VIE"},
]

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "prices.db"
REPORT_PATH = ROOT / "report.html"
LOG_PATH = ROOT / "flight-tracker.log"
```

- [ ] **Step 4: Napíš padajúci test `tests/test_db.py`**

```python
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
```

- [ ] **Step 5: Spusti test — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_db.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tracker.db'` alebo `AttributeError`).

- [ ] **Step 6: Implementuj `tracker/db.py`**

```python
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
```

- [ ] **Step 7: Spusti test — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_db.py -v`
Expected: PASS (2 passed).

- [ ] **Step 8: Commit**

```bash
cd ~/www/flight-tracker
git add requirements.txt tracker/__init__.py tracker/config.py tracker/db.py tests/test_db.py
git commit -m "feat: db layer and project config"
```

---

### Task 2: Ryanair klient a parsovanie

**Files:**
- Create: `tracker/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: nič z iných modulov.
- Produces:
  - `fetch.parse_fares(payload: dict, direction: str) -> list[dict]` — z JSON odpovede vytvorí záznamy `{direction, flight_date, flight_number, price, seats_left}` (seats_left vždy None).
  - `fetch.days_in_month(year: int, month: int) -> list[str]` — zoznam ISO dátumov ("YYYY-MM-DD") všetkých dní mesiaca.
  - `fetch.fetch_day(origin, destination, day, session=None, currency="EUR") -> dict` — vráti naparsovaný JSON; `session` je objekt s metódou `.get(...)` (default modul `requests`).
  - `fetch.fetch_leg(origin, destination, direction, year, month, session=None) -> list[dict]` — záznamy za celý mesiac jedného smeru.

- [ ] **Step 1: Napíš padajúci test `tests/test_fetch.py`**

```python
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
```

- [ ] **Step 2: Spusti test — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_fetch.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tracker.fetch'`).

- [ ] **Step 3: Implementuj `tracker/fetch.py`**

```python
from datetime import date, timedelta

import requests

BASE_URL = "https://services-api.ryanair.com/farfnd/v4/oneWayFares"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
TIMEOUT = 20


def parse_fares(payload, direction):
    records = []
    for fare in payload.get("fares", []):
        ob = fare["outbound"]
        records.append(
            {
                "direction": direction,
                "flight_date": ob["departureDate"][:10],
                "flight_number": ob["flightNumber"],
                "price": ob["price"]["value"],
                "seats_left": None,
            }
        )
    return records


def days_in_month(year, month):
    days = []
    d = date(year, month, 1)
    while d.month == month:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def fetch_day(origin, destination, day, session=None, currency="EUR"):
    client = session or requests
    params = {
        "departureAirportIataCode": origin,
        "arrivalAirportIataCode": destination,
        "outboundDepartureDateFrom": day,
        "outboundDepartureDateTo": day,
        "currency": currency,
    }
    resp = client.get(BASE_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_leg(origin, destination, direction, year, month, session=None, currency="EUR"):
    records = []
    for day in days_in_month(year, month):
        payload = fetch_day(origin, destination, day, session=session, currency=currency)
        records.extend(parse_fares(payload, direction))
    return records
```

- [ ] **Step 4: Spusti test — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_fetch.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/fetch.py tests/test_fetch.py
git commit -m "feat: ryanair farfnd client and fare parsing"
```

---

### Task 3: Orchestrácia zberu (collect)

**Files:**
- Create: `tracker/collect.py`
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: `db.insert_observations`, `fetch.fetch_leg`, `config.LEGS/YEAR/MONTH/CURRENCY`.
- Produces:
  - `collect.collect_once(conn, observed_at, legs=None, year=None, month=None, currency=None, session=None) -> int` — zozbiera záznamy zo všetkých nôh a urobí JEDEN insert; vráti počet zapísaných riadkov. Ak ktorákoľvek noha vyhodí výnimku, propaguje ju a NIČ nezapíše.

- [ ] **Step 1: Napíš padajúci test `tests/test_collect.py`**

```python
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
```

- [ ] **Step 2: Spusti test — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_collect.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tracker.collect'`).

- [ ] **Step 3: Implementuj `tracker/collect.py`**

```python
from . import config, db, fetch


def collect_once(conn, observed_at, legs=None, year=None, month=None,
                 currency=None, session=None):
    legs = legs if legs is not None else config.LEGS
    year = year if year is not None else config.YEAR
    month = month if month is not None else config.MONTH
    currency = currency if currency is not None else config.CURRENCY

    records = []
    for leg in legs:
        records.extend(
            fetch.fetch_leg(
                leg["origin"], leg["destination"], leg["direction"],
                year, month, session=session, currency=currency,
            )
        )
    # vsetky volania presli -> az teraz jeden transakcny insert
    return db.insert_observations(conn, observed_at, records)
```

- [ ] **Step 4: Spusti test — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_collect.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/collect.py tests/test_collect.py
git commit -m "feat: collect orchestration with atomic write"
```

---

### Task 4: Štatistiky (čisté funkcie)

**Files:**
- Create: `tracker/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: nič (pracuje nad list[dict] riadkov v tvare z `db.all_rows`).
- Produces:
  - `stats.latest_observed_at(rows) -> str | None`.
  - `stats.price_series(rows, direction) -> dict[str, list[tuple[str, float]]]` — mapuje `flight_date -> [(observed_at, price), ...]` zoradené podľa času.
  - `stats.cheapest_roundtrip_now(rows, max_results=10) -> list[dict]` — kombinácie z NAJNOVŠIEHO merania; každá `{out_date, out_price, ret_date, ret_price, total}`, návrat nesmie byť pred odletom, zoradené podľa `total`.
  - `stats.cheapest_roundtrip_over_time(rows) -> list[tuple[str, float]]` — `(observed_at, najlacnejsi_total)` pre každé meranie.

- [ ] **Step 1: Napíš padajúci test `tests/test_stats.py`**

```python
from tracker import stats

ROWS = [
    # meranie 14:00
    {"observed_at": "2026-06-30T14:00", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 35.0},
    {"observed_at": "2026-06-30T14:00", "direction": "RET", "flight_date": "2026-09-30", "flight_number": "FR7311", "price": 98.0},
    {"observed_at": "2026-06-30T14:00", "direction": "RET", "flight_date": "2026-09-20", "flight_number": "FR7311", "price": 50.0},
    # meranie 15:00 (OUT zlacnel)
    {"observed_at": "2026-06-30T15:00", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 30.0},
    {"observed_at": "2026-06-30T15:00", "direction": "RET", "flight_date": "2026-09-30", "flight_number": "FR7311", "price": 98.0},
]


def test_latest_observed_at():
    assert stats.latest_observed_at(ROWS) == "2026-06-30T15:00"
    assert stats.latest_observed_at([]) is None


def test_price_series_groups_by_flight_date_sorted():
    series = stats.price_series(ROWS, "OUT")
    assert series == {"2026-09-26": [("2026-06-30T14:00", 35.0), ("2026-06-30T15:00", 30.0)]}


def test_cheapest_roundtrip_now_excludes_return_before_outbound():
    combos = stats.cheapest_roundtrip_now(ROWS)
    # najnovsie meranie 15:00 ma OUT 26.9. a RET 30.9. -> jedina platna kombinacia
    assert combos == [
        {"out_date": "2026-09-26", "out_price": 30.0,
         "ret_date": "2026-09-30", "ret_price": 98.0, "total": 128.0}
    ]


def test_cheapest_roundtrip_over_time():
    series = stats.cheapest_roundtrip_over_time(ROWS)
    # 14:00: OUT 35 + RET 98 (RET 20.9 je pred odletom -> neplatny) = 133
    # 15:00: OUT 30 + RET 98 = 128
    assert series == [("2026-06-30T14:00", 133.0), ("2026-06-30T15:00", 128.0)]
```

- [ ] **Step 2: Spusti test — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_stats.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tracker.stats'`).

- [ ] **Step 3: Implementuj `tracker/stats.py`**

```python
from collections import defaultdict


def latest_observed_at(rows):
    return max((r["observed_at"] for r in rows), default=None)


def price_series(rows, direction):
    series = defaultdict(list)
    for r in sorted(rows, key=lambda x: x["observed_at"]):
        if r["direction"] == direction:
            series[r["flight_date"]].append((r["observed_at"], r["price"]))
    return dict(series)


def cheapest_roundtrip_now(rows, max_results=10):
    ts = latest_observed_at(rows)
    if ts is None:
        return []
    out = [r for r in rows if r["observed_at"] == ts and r["direction"] == "OUT"]
    ret = [r for r in rows if r["observed_at"] == ts and r["direction"] == "RET"]
    combos = []
    for o in out:
        for b in ret:
            if b["flight_date"] >= o["flight_date"]:  # navrat nie pred odletom
                combos.append(
                    {
                        "out_date": o["flight_date"],
                        "out_price": o["price"],
                        "ret_date": b["flight_date"],
                        "ret_price": b["price"],
                        "total": round(o["price"] + b["price"], 2),
                    }
                )
    combos.sort(key=lambda c: c["total"])
    return combos[:max_results]


def cheapest_roundtrip_over_time(rows):
    by_ts = defaultdict(list)
    for r in rows:
        by_ts[r["observed_at"]].append(r)
    series = []
    for ts in sorted(by_ts):
        best = cheapest_roundtrip_now(by_ts[ts], max_results=1)
        if best:
            series.append((ts, best[0]["total"]))
    return series
```

- [ ] **Step 4: Spusti test — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_stats.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/stats.py tests/test_stats.py
git commit -m "feat: stats functions for series and cheapest roundtrip"
```

---

### Task 5: HTML report (Plotly)

**Files:**
- Create: `tracker/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `stats.price_series`, `stats.cheapest_roundtrip_now`, `stats.cheapest_roundtrip_over_time`, `stats.latest_observed_at`.
- Produces:
  - `report.build_report_html(rows: list[dict]) -> str` — kompletný HTML dokument so 3 sekciami: graf vývoja ceny (OUT+RET), tabuľka najlacnejších round-tripov teraz, graf najlacnejšieho round-tripu v čase. Pri prázdnych dátach vráti HTML s textom "Zatiaľ žiadne dáta".
  - `report.write_report(rows, path) -> None` — zapíše výstup `build_report_html` do súboru.

- [ ] **Step 1: Napíš padajúci test `tests/test_report.py`**

```python
from tracker import report

ROWS = [
    {"observed_at": "2026-06-30T14:00", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 35.0},
    {"observed_at": "2026-06-30T14:00", "direction": "RET", "flight_date": "2026-09-30", "flight_number": "FR7311", "price": 98.0},
]


def test_build_report_html_contains_sections_and_total():
    html = report.build_report_html(ROWS)
    assert "<html" in html.lower()
    assert "Vývoj ceny" in html
    assert "Najlacnejší round-trip" in html
    assert "133" in html  # 35 + 98 v tabulke


def test_build_report_html_handles_empty():
    html = report.build_report_html([])
    assert "Zatiaľ žiadne dáta" in html


def test_write_report_creates_file(tmp_path):
    out = tmp_path / "report.html"
    report.write_report(ROWS, out)
    assert out.exists()
    assert "Vývoj ceny" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Spusti test — musí zlyhať**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_report.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tracker.report'`).

- [ ] **Step 3: Implementuj `tracker/report.py`**

```python
from pathlib import Path

import plotly.graph_objects as go

from . import stats


def _price_evolution_fig(rows):
    fig = go.Figure()
    for direction, label in (("OUT", "VIE→EFL"), ("RET", "EFL→VIE")):
        for flight_date, points in sorted(stats.price_series(rows, direction).items()):
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers",
                                     name=f"{label} {flight_date}"))
    fig.update_layout(title="Vývoj ceny v čase",
                      xaxis_title="Čas merania", yaxis_title="Cena (EUR)")
    return fig


def _best_over_time_fig(rows):
    series = stats.cheapest_roundtrip_over_time(rows)
    xs = [s[0] for s in series]
    ys = [s[1] for s in series]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines+markers",
                               name="Najlacnejší round-trip"))
    fig.update_layout(title="Najlacnejší round-trip v čase",
                      xaxis_title="Čas merania", yaxis_title="Total (EUR)")
    return fig


def _combos_table_html(rows):
    combos = stats.cheapest_roundtrip_now(rows)
    head = ("<tr><th>Odlet (VIE→EFL)</th><th>Cena tam</th>"
            "<th>Návrat (EFL→VIE)</th><th>Cena späť</th><th>Spolu</th></tr>")
    body = "".join(
        f"<tr><td>{c['out_date']}</td><td>{c['out_price']:.2f}</td>"
        f"<td>{c['ret_date']}</td><td>{c['ret_price']:.2f}</td>"
        f"<td><b>{c['total']:.2f}</b></td></tr>"
        for c in combos
    )
    return f"<table border='1' cellpadding='6'>{head}{body}</table>"


def build_report_html(rows):
    if not rows:
        return ("<html><head><meta charset='utf-8'></head>"
                "<body><h1>Vývoj ceny</h1><p>Zatiaľ žiadne dáta</p></body></html>")

    updated = stats.latest_observed_at(rows)
    evolution = _price_evolution_fig(rows).to_html(full_html=False, include_plotlyjs="cdn")
    best = _best_over_time_fig(rows).to_html(full_html=False, include_plotlyjs=False)
    table = _combos_table_html(rows)

    return f"""<html>
<head><meta charset='utf-8'><title>Ryanair VIE↔EFL tracker</title></head>
<body>
<h1>Ryanair VIE↔EFL — september 2026</h1>
<p>Posledná aktualizácia: {updated}</p>
<h2>Vývoj ceny v čase</h2>
{evolution}
<h2>Najlacnejší round-trip teraz</h2>
{table}
<h2>Najlacnejší round-trip v čase</h2>
{best}
</body>
</html>"""


def write_report(rows, path):
    Path(path).write_text(build_report_html(rows), encoding="utf-8")
```

- [ ] **Step 4: Spusti test — musí prejsť**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest tests/test_report.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/report.py tests/test_report.py
git commit -m "feat: html report with plotly charts"
```

---

### Task 6: Runner, launchd agent a README

**Files:**
- Create: `tracker/run.py`
- Create: `com.flighttracker.hourly.plist`
- Create: `README.md`
- Create: `.gitignore`

**Interfaces:**
- Consumes: `config`, `db.connect/init_db/all_rows`, `collect.collect_once`, `report.write_report`.
- Produces: `tracker/run.py` spustiteľný cez `python -m tracker.run` — jeden hodinový cyklus s logovaním a skip-on-error.

- [ ] **Step 1: Implementuj `tracker/run.py`**

```python
import logging
from datetime import datetime

from . import collect, config, db, report


def main():
    logging.basicConfig(
        filename=str(config.LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    observed_at = datetime.now().isoformat(timespec="minutes")
    conn = db.connect(config.DB_PATH)
    db.init_db(conn)

    try:
        n = collect.collect_once(conn, observed_at)
        logging.info("collected %d rows at %s", n, observed_at)
    except Exception as exc:  # zlyhanie zberu -> nic nezapisane, skus o hodinu
        logging.error("collect failed at %s: %s", observed_at, exc)
        return

    rows = db.all_rows(conn)
    report.write_report(rows, config.REPORT_PATH)
    logging.info("report written to %s (%d total rows)", config.REPORT_PATH, len(rows))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Vytvor venv a over runner (jeden ostrý beh)**

Run:
```bash
cd ~/www/flight-tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m tracker.run
```
Expected: vznikne `prices.db` aj `report.html`, do `flight-tracker.log` pribudne riadok "collected N rows". Otvor `report.html` v prehliadači a over, že vidíš grafy.

- [ ] **Step 3: Vytvor `.gitignore`**

```text
__pycache__/
*.pyc
.venv/
prices.db
report.html
flight-tracker.log
launchd.out.log
launchd.err.log
```

- [ ] **Step 4: Vytvor `com.flighttracker.hourly.plist`**

> Nahraď `/Users/hujerko` skutočnou cestou ak treba; `which python3` ti dá cestu k interpreteru — vlož ju do prvého `<string>`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.flighttracker.hourly</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/hujerko/www/flight-tracker/.venv/bin/python</string>
        <string>-m</string>
        <string>tracker.run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/hujerko/www/flight-tracker</string>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/hujerko/www/flight-tracker/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/hujerko/www/flight-tracker/launchd.err.log</string>
</dict>
</plist>
```

- [ ] **Step 5: Nainštaluj launchd agent**

Run:
```bash
cp ~/www/flight-tracker/com.flighttracker.hourly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.flighttracker.hourly.plist
launchctl list | grep flighttracker
```
Expected: v zozname sa objaví `com.flighttracker.hourly`. `RunAtLoad` spustí prvý beh hneď — po chvíli skontroluj `flight-tracker.log` a `report.html`.

> Pozn.: plist ukazuje na `.venv/bin/python`, kde sú nainštalované `requests`/`plotly` (Task 6 Step 2). Ak presunieš projekt, uprav cestu v plist aj `WorkingDirectory`.

- [ ] **Step 6: Vytvor `README.md`**

```markdown
# Ryanair Price Tracker (VIE ↔ EFL)

Sleduje každú hodinu ceny letov Ryanair Viedeň ↔ Kefalonia za september 2026,
ukladá históriu do SQLite a generuje `report.html` s grafmi. Bez LLM.

## Inštalácia
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

## Jeden beh manuálne
    .venv/bin/python -m tracker.run

Vytvorí/aktualizuje `prices.db` a `report.html`. Report otvor v prehliadači.

## Hodinové spúšťanie (macOS launchd)
    cp com.flighttracker.hourly.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.flighttracker.hourly.plist

Odpojenie:
    launchctl unload ~/Library/LaunchAgents/com.flighttracker.hourly.plist

## Konfigurácia
Trasu a sledované okno zmeníš v `tracker/config.py` (LEGS, YEAR, MONTH).

## Testy
    .venv/bin/python -m pytest -v

## Zdroj dát
Verejný endpoint `services-api.ryanair.com/farfnd/v4/oneWayFares`, volaný deň po dni.
Neoficiálny — Ryanair ho môže zmeniť. `seats_left` endpoint nevracia (ostáva NULL).
```

- [ ] **Step 7: Spusti všetky testy**

Run: `cd ~/www/flight-tracker && .venv/bin/python -m pytest -v`
Expected: PASS (všetky testy zo všetkých súborov zelené).

- [ ] **Step 8: Commit**

```bash
cd ~/www/flight-tracker
git add tracker/run.py com.flighttracker.hourly.plist README.md .gitignore
git commit -m "feat: hourly runner, launchd agent and docs"
```

---

## Self-Review

**1. Spec coverage:**
- Trasa VIE↔EFL obojsmerne → `config.LEGS` (Task 1), `fetch_leg` (Task 2). ✓
- Flexibilné okno september → `days_in_month` + zber deň po dni (Task 2/3). ✓
- 1 osoba, lineárne ceny → ukladáme cenu za 1 os.; round-trip = súčet (Task 4). ✓
- Hodinový beh, lokálne (launchd) → `run.py` + plist (Task 6). ✓
- SQLite história append-only → schéma + insert (Task 1). ✓
- 3 grafy/štatistiky → `report.py` (Task 5). ✓
- Skip-on-error, nič sa nezapíše → atomický collect (Task 3) + try/except v runneri (Task 6). ✓
- `seats_left` NULL → default None v insert (Task 1), parse (Task 2). ✓
- Zdroj `farfnd` deň po dni, slušný User-Agent → `fetch.py` (Task 2). ✓

**2. Placeholder scan:** Žiadne TBD/TODO; každý krok má reálny kód a príkazy. ✓

**3. Type consistency:** record kľúče `direction/flight_date/flight_number/price/seats_left` konzistentné naprieč db/fetch/collect; combo kľúče `out_date/out_price/ret_date/ret_price/total` konzistentné medzi stats a report. ✓
