# Ryanair Price Tracker (BUD ↔ PVK)

Sleduje každé 2 hodiny cenu **jedného fixného letu** Ryanair
**Budapešť (BUD) ↔ Lefkada (PVK), 6.–13. 9. 2026**, ukladá históriu do SQLite
a generuje `report.html`. Bez LLM.

> Viedeň je vypnutá (`DESTINATIONS = []`). Ubytovanie je zaplatené na fixný
> termín 6. 9. a VIE↔PVK lieta stredy a soboty — na náš termín teda spoj
> neexistuje. Sken celého mesiaca preto nemá zmysel: beh je dnes 4 requesty
> namiesto 62. Historické VIE dáta v `prices.db` ostávajú, report ich neukazuje.

## Inštalácia
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

## Jeden beh manuálne
    .venv/bin/python -m tracker.run

Vytvorí/aktualizuje `prices.db` a `report.html`. Report otvor v prehliadači.

Report je jedna karta o našom lete: cena/os, prepínač počtu osôb, verdikt
(percentil voči histórii), rozsah za 7 dní, zmena za 24 h, dní do odletu a graf
vývoja. Layout je responzívny — overené pri 320 / 390 / 768 px bez vodorovného
scrollu.

## Pravidelné spúšťanie — GitHub Actions + Pages (primárne)
Workflow `.github/workflows/track.yml` beží každé 2 hodiny (cron, UTC):
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

## Telegram alerty
`tracker/notify.py` sleduje výhradne náš fixný let (`PRIMARY_TRIP`) a po každom
behu vyhodnotí **tri nezávislé signály**:

| Signál | Kedy | Správa |
|--------|------|--------|
| `target` | cena ≤ `ALERT_TARGET_EUR` (140 €/os) | ✅ / 🔥 kupuj |
| `window_low` | najnižšie za posledných N dní, **aj nad cieľom** | 📉 príležitosť |
| `spike` | rast ≥ `ALERT_SPIKE_PCT` (8 %) za 24 h | 📈 okno sa zatvára |
| `digest` | `HEARTBEAT_HOURS` (24 h) neprišlo nič | 📊 denný súhrn |

Pošle sa **prvý signál, ktorý prejde cooldownom** (`ALERT_COOLDOWN_HOURS`), takže
jedno meranie nikdy nepošle dve správy. Keď je signál v cooldowne, padá sa na
ďalší v poradí — nový nižší prepad sa teda neutopí.

Okno pre `window_low` sa **skracuje na `ALERT_WINDOW_DAYS_NEAR` (10 dní)**, keď je
do odletu menej než `NEAR_DEPARTURE_DAYS` (30) — vtedy sa už čakať nedá.

> Pôvodne bola jediná podmienka „nové **absolútne** minimum A ZÁROVEŇ ≤ cieľ". Tá sa
> po zásahu historického minima (126,57 € dňa 13. 7.) natrvalo zamkla a alert prestal
> chodiť — aj výborná cena 135 € by už neposlala nič. Preto sú signály rozbité.

`digest` je poistka proti ticheu: keď `HEARTBEAT_HOURS` neprišiel žiadny alert,
pošle sa súhrn (aktuálna cena, rozsah za 7 dní, zmena za 24 h, percentil voči celej
histórii, dní do odletu). Ticho tak nikdy neznamená „asi je to pokazené".

Odoslané alerty sa zapisujú do tabuľky `alerts` v `prices.db` (odtiaľ cooldown
aj heartbeat).

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
Destinácie a okno v `tracker/config.py` (`ORIGIN`, `DESTINATIONS`, `YEAR`, `MONTH`,
`STAY_PRESETS`, `PERSONS`, `EXTRAS_EUR`, `INCLUDE_EXTRAS`, `REFERENCE_PRICE_EUR`,
`ALERT_TARGET_EUR`). Pridanie destinácie = jeden záznam `{code, label}` v `DESTINATIONS`.

## Testy
    .venv/bin/python -m pytest -v

## Zdroj dát
Verejný endpoint `services-api.ryanair.com/farfnd/v4/oneWayFares`, volaný deň po dni.
Neoficiálny — Ryanair ho môže zmeniť. `seats_left` endpoint nevracia (ostáva NULL).

### Prečo nemáme presný počet sedadiel
Počet voľných miest („zostávajú len 2 sedadlá za túto cenu") vracia iný endpoint —
`www.ryanair.com/api/booking/v4/.../availability` (`faresLeft`). Ten je za anti-botom
(Akamai, HTTP 409 „Availability declined") a z cloud cronu / servera sa spoľahlivo
volať nedá. Preto namiesto presného čísla používame **heuristiku**: keď je cena nášho
letu na historickom minime (= najlacnejší fare bucket, ktorý typicky máva len pár
miest), report aj Telegram alert pridajú upozornenie „over počet a rezervuj hneď"
(text v `config.SEATS_HINT`). Nie je to presné číslo, ale rieši to reálnu otázku:
_treba konať rýchlo?_
