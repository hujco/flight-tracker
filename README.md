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
