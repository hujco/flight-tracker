# Multi-destination Tracking — Design

**Date:** 2026-06-30
**Status:** Approved

## Goal

Rozšíriť tracker z jednej destinácie (Kefalonia) na **tri**: Kefalonia (EFL),
Lefkada (letisko Preveza/Aktion, PVK) a Zakyntos (ZTH) — všetko Ryanair z Viedne (VIE),
obojsmerne, pobyt 7/9/10 nocí, pre 2 osoby. Report s prepínačom destinácií;
Telegram alert per destinácia.

## Rozsah

- **Origin:** VIE. **Destinácie:** EFL, PVK, ZTH.
- Round-trip sa páruje **v rámci tej istej destinácie** (VIE→X tam, X→VIE späť).
- Referencia (~301 €/2 os., ~117 €/os) aj alert cieľ (130 €/os) sú **globálne**,
  platia rovnako pre každú destináciu (trasy sú cenovo porovnateľné).
- Pobytové presety 7/9/10 nocí ostávajú.

## Dátový model

Do tabuľky `prices` pribudne stĺpec **`destination`** (IATA: `EFL`/`PVK`/`ZTH`).

| stĺpec | popis |
|---|---|
| `observed_at` | čas merania |
| `destination` | **nový** — IATA cieľa (EFL/PVK/ZTH) |
| `direction` | `OUT` = VIE→destinácia, `RET` = destinácia→VIE |
| `flight_date`, `flight_number`, `price`, `seats_left` | ako doteraz |

**Migrácia (idempotentná, beží pri každom `init_db`):** ak stĺpec `destination`
chýba → `ALTER TABLE prices ADD COLUMN destination TEXT` a
`UPDATE prices SET destination='EFL' WHERE destination IS NULL` (existujúce dáta
sú všetko Kefalonia). Beží aj v CI nad commitnutou `prices.db`.

Index sa rozšíri na `(destination, direction, flight_date, observed_at)`.

## Config

```python
ORIGIN = "VIE"
DESTINATIONS = [
    {"code": "EFL", "label": "Kefalonia"},
    {"code": "PVK", "label": "Lefkada"},    # letisko Preveza/Aktion
    {"code": "ZTH", "label": "Zakyntos"},
]
```

`LEGS` sa odvodí z `DESTINATIONS` (pre každú destináciu OUT a RET).
Globálne ostáva: `STAY_PRESETS`, `PERSONS`, `EXTRAS_EUR`, `INCLUDE_EXTRAS`,
`REFERENCE_PRICE_EUR`, `REFERENCE_PER_PERSON_EUR`, `ALERT_TARGET_EUR`,
`TELEGRAM_CHAT_ID`, `REPORT_URL`.

## Zber (collect/fetch)

`collect_once` prejde **destinácie × {OUT, RET} × dni mesiaca** (~3×2×30 = 180
volaní za beh, sekvenčne). Každý záznam dostane svoju `destination`. Atomicita
ostáva: najprv sa zozbierajú všetky záznamy, potom jeden transakčný insert.
`fetch.parse_fares` / `fetch_leg` dostanú `destination` a vložia ho do záznamov.

## Štatistiky (bez zmeny logiky)

`stats.py` ostáva **nezmenené**. Report aj alert si **najprv odfiltrujú riadky na
jednu destináciu** a potom volajú existujúce `cheapest_roundtrip_now` /
`cheapest_roundtrip_over_time` / `cheapest_leg_over_time` / `price_series`.
Tým sa OUT/RET párujú vždy len v rámci tej destinácie.

## Report

Dvojúrovňový prepínač:
- **Hore prepínač destinácií** (Kefalonia / Lefkada / Zakyntos).
- Vnútri vybranej destinácie **existujúci prepínač 7/9/10 nocí** + KPI karty,
  tabuľka „najlacnejší round-trip teraz", graf „cena v čase" a graf „round-trip v čase".

Všetko (3 destinácie × 3 presety) sa predpočíta do HTML; prepína sa JS
(skryté `hidden` divy + resize Plotly pri prepnutí). plotly.js raz v `<head>`.
EU formát dátumov ostáva. Referencia/verdikt (~117 €/os) sa uplatní na každú
destináciu rovnako (default `INCLUDE_EXTRAS=False`, len letenky).

## Alert (per destinácia)

`maybe_notify` prejde každú destináciu zvlášť:
1. odfiltruje riadky na destináciu,
2. `detect_new_low` nad históriou tej destinácie (najlacnejšia/os naprieč
   STAY_PRESETS, nové minimum a ≤ `ALERT_TARGET_EUR`),
3. ak vyletí, pošle Telegram správu **s názvom ostrova** (napr.
   „🔥 Lefkada: 119 €/os …"). Viac destinácií naraz = viac správ.

`send_test` aj env/secret logika (`TELEGRAM_TOKEN`, chat id z configu) ostávajú.

## Ošetrenie chýb

Ako doteraz: zlyhanie endpointu → beh sa preskočí, nič sa nezapíše (atomicky);
zlyhanie alertu sa zaloguje a nezhodí beh. Ak Ryanair niektorú destináciu/deň
nelieta, `fares` je prázdne → žiadne riadky (korektné).

## Testy

- Migrácia: starý DB bez `destination` → po `init_db` majú existujúce riadky `EFL`,
  nové vkladané majú svoju destináciu.
- `db.insert_observations` ukladá a vracia `destination`.
- `fetch.parse_fares` / `fetch_leg` značia destináciu.
- `collect_once` zozbiera všetky destinácie × smery, atomicita pri zlyhaní.
- Round-trip sa páruje len v rámci destinácie (filter + existujúce stats).
- `notify.maybe_notify` rieši nové minimum per destinácia (správa menuje ostrov).
- Report obsahuje 3 prepínače destinácií a pre každú presety/KPI.

## Mimo rozsahu (YAGNI)

- Žiadne iné aerolínie (len Ryanair), žiadny iný origin než VIE.
- Žiadne per-destinácia rôzne referencie/ciele (globálne stačia).
- Žiadne porovnávacie súhrnné dashboardy naprieč destináciami (len prepínač).
