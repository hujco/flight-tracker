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

## Telegram alert pri dobrej cene
`tracker/notify.py` po každom behu pošle Telegram správu, keď najlacnejšia
letenka/os (naprieč `STAY_PRESETS`) klesne na **nové minimum** a zároveň je
**≤ `ALERT_TARGET_EUR`** (default 130 €). Bez nového minima alebo nad cieľom
nepošle nič (žiadny spam). Cena ≤ `REFERENCE_PER_PERSON_EUR` sa v správe
označí ako „🔥 skvelá".

Nastavenie (jednorazovo):
1. V Telegrame napíš **@BotFather** → `/newbot` → získaš **bot token**.
2. Napíš svojmu novému botovi hocičo (napr. „ahoj"), potom otvor
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → nájdi `chat.id`.
3. V repo **Settings → Secrets and variables → Actions** pridaj:
   - `TELEGRAM_TOKEN` = bot token
   - `TELEGRAM_CHAT_ID` = tvoje chat id
Workflow ich podá ako env; bez nich alert ticho spí, tracker beží ďalej.

Cieľovú cenu zmeníš v `tracker/config.py` (`ALERT_TARGET_EUR`).

## Konfigurácia
Trasu a okno zmeníš v `tracker/config.py` (LEGS, YEAR, MONTH, STAY_PRESETS,
PERSONS, EXTRAS_EUR, INCLUDE_EXTRAS, REFERENCE_PRICE_EUR, ALERT_TARGET_EUR).

## Testy
    .venv/bin/python -m pytest -v

## Zdroj dát
Verejný endpoint `services-api.ryanair.com/farfnd/v4/oneWayFares`, volaný deň po dni.
Neoficiálny — Ryanair ho môže zmeniť. `seats_left` endpoint nevracia (ostáva NULL).
