# Ryanair Price Tracker — Design

**Date:** 2026-06-30
**Status:** Approved

## Goal

Sledovať každú hodinu ceny letov Ryanair na trase **Viedeň (VIE) ↔ Kefalonia (EFL)** za
celý **september 2026**, obojsmerne, pre 1 osobu. Ukladať históriu cien a generovať
grafy/štatistiky o ich vývoji.

Žiadne LLM — ide o deterministický zber dát a vizualizáciu.

## Rozsah (scope)

- **Trasa:** VIE → EFL (tam) a EFL → VIE (späť). Round-trip ceny sa skladajú pri zobrazení
  (ľubovoľný odlet + ľubovoľný návrat = súčet cien dvoch one-way letov).
- **Okno:** flexibilné — všetky dostupné lety v septembri 2026.
- **Cestujúci:** 1 dospelý. Ceny Ryanairu sú lineárne, takže pre N osôb = cena × N
  (rieši sa pri zobrazení, nie pri zbere).
- **Interval:** každú hodinu.
- **Beh:** lokálne na always-on Macu (launchd), nie cloud.

## Architektúra

```
launchd (každú hodinu)
        │
        ▼
  fetch.py ──► Ryanair availability API (VIE→EFL, EFL→VIE, celý september)
        │
        ▼
  prices.db (SQLite) ──► história každej ceny
        │
        ▼
  report.py ──► report.html (grafy)
```

Dva oddelené Python skripty s jasnou zodpovednosťou:

- **`fetch.py`** — zavolá Ryanair endpoint pre obe nohy, naparsuje JSON, zapíše riadky do SQLite.
  Závisí len na: HTTP klient (`requests`/`httpx`) + `sqlite3` (std lib).
- **`report.py`** — číta z SQLite, počíta štatistiky a round-trip kombinácie, vygeneruje
  `report.html`. Závisí len na: SQLite + charting (Plotly offline / Chart.js cez šablónu).

Skripty komunikujú výhradne cez SQLite súbor — dajú sa spúšťať a testovať nezávisle.

## Zdroj dát

Ryanair neoficiálny (ale roky stabilný) JSON endpoint, žiadny API kľúč:

- **`https://www.ryanair.com/api/booking/v4/availability`** — ceny pre rozsah dní danej trasy.
  Parametre okrem iného: `Origin`, `Destination`, `DateOut`, `FlexDaysOut`/`FlexDaysBeforeOut`
  (rozsah ±dní), `ADT=1` (1 dospelý), `RoundTrip=false`, `ToUs=AGREED`.
  Cez celý september sa pokryje viacerými volaniami (FlexDays má strop ~6 dní na stranu).
- Pomocný/overovací: `https://services-api.ryanair.com/farfnd/v4/oneWayFares` (vracia len
  najlacnejší jeden let za okno — **nestačí** na flexibilné okno, slúži len na sanity-check).

Slušné správanie: rozumný `User-Agent`, len nevyhnutné requesty za beh (jeden hodinový beh =
zopár volaní), žiadne paralelné búšenie.

## Dátový model

Jedna tabuľka, append-only časový rad. Round-trip ceny sa NEpočítajú pri ukladaní.

**Tabuľka `prices`:**

| stĺpec | typ | popis |
|---|---|---|
| `id` | INTEGER PK | |
| `observed_at` | TEXT (ISO) | čas merania = čas behu skriptu |
| `direction` | TEXT | `OUT` (VIE→EFL) / `RET` (EFL→VIE) |
| `flight_date` | TEXT (date) | dátum letu |
| `flight_number` | TEXT | napr. FR7310 |
| `price` | REAL | cena za 1 osobu v EUR |
| `seats_left` | INTEGER | zostávajúce sedadlá, ak endpoint vráti (inak NULL) |

Index na `(direction, flight_date, observed_at)` pre rýchle grafy.

## Vizualizácia (`report.html`)

1. **Vývoj ceny v čase** — čiarový graf, jedna čiara na každý dátum letu (zvlášť OUT a RET).
   Ukazuje trend hodinu po hodine.
2. **Najlacnejší round-trip teraz** — tabuľka top kombinácií odlet+návrat s celkovou cenou
   (najnovšie odmerané ceny).
3. **Najlacnejší round-trip v čase** — ako sa najlepšia možná kombinácia hýbala odkedy
   beží sledovanie.

Statická HTML, pregeneruje sa pri každom behu, otvára sa priamo v prehliadači.

## Ošetrenie chýb

- Endpoint zlyhá / timeout / neočakávaný JSON → beh sa preskočí, zaloguje sa chyba,
  **nič sa nezapíše** (žiadne falošné/čiastočné dáta). Ďalší pokus o hodinu.
- Zápis do DB je transakčný — buď celá sada riadkov behu, alebo nič.
- Logy do `flight-tracker.log` (čas, počet zapísaných riadkov alebo chyba).

## Spúšťanie

- **`launchd`** agent (`~/Library/LaunchAgents/...plist`), `StartInterval` / `StartCalendarInterval`
  na 1 hodinu. Spoľahlivejší než cron pri budení/logovaní na macOS.
- Agent spustí `fetch.py` a po ňom `report.py` (alebo jeden wrapper, čo zavolá oboje).
- stdout/stderr presmerované do log súboru.

## Mimo rozsahu (YAGNI)

- Žiadne notifikácie/alerty pri poklese ceny (dá sa pridať neskôr).
- Žiadne iné trasy ani aerolínie.
- Žiadne LLM zhrnutia.
- Žiadny cloud/always-on hosting — beží lokálne.
