# Ryanair Price Tracker (VIE ↔ EFL)

Sleduje každú hodinu ceny letov Ryanair Viedeň ↔ Kefalonia za september 2026,
ukladá históriu do SQLite a generuje `report.html` s grafmi. Bez LLM.

## Inštalácia
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

## Jeden beh manuálne
    .venv/bin/python -m tracker.run

Vytvorí/aktualizuje `prices.db` a `report.html`. Report otvor v prehliadači.

## Hodinové spúšťanie — GitHub Actions + Pages (primárne)
Workflow `.github/workflows/track.yml` beží každú hodinu (cron, UTC):
stiahne ceny, commitne `prices.db` späť do repa (rastúca história) a
publikuje report na **GitHub Pages**. Beží v cloude, nezávisí od zapnutého Macu.

- Report URL: `https://hujco.github.io/flight-tracker/`
- Manuálne spustenie: `gh workflow run track.yml` (alebo tlačidlo "Run workflow" v Actions).
- Pages musí byť nastavené na zdroj **GitHub Actions** (Settings → Pages → Source: GitHub Actions).

História cien (`prices.db`) je verzovaná priamo v repe.

## Hodinové spúšťanie — lokálne (macOS launchd, alternatíva)
    cp com.flighttracker.hourly.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.flighttracker.hourly.plist
Odpojenie:
    launchctl unload ~/Library/LaunchAgents/com.flighttracker.hourly.plist

> Nepoužívaj lokálny aj cloudový beh naraz nad tým istým repom — divergovala by `prices.db`.

## Konfigurácia
Trasu a okno zmeníš v `tracker/config.py` (LEGS, YEAR, MONTH, MIN/MAX_NIGHTS,
PERSONS, EXTRAS_EUR, REFERENCE_PRICE_EUR).

## Testy
    .venv/bin/python -m pytest -v

## Zdroj dát
Verejný endpoint `services-api.ryanair.com/farfnd/v4/oneWayFares`, volaný deň po dni.
Neoficiálny — Ryanair ho môže zmeniť. `seats_left` endpoint nevracia (ostáva NULL).
