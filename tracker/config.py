from datetime import date
from pathlib import Path

YEAR = 2026
MONTH = 9
CURRENCY = "EUR"

# Dĺžka pobytu pre round-trip: prepínateľné presety (počet nocí, vrátane hraníc)
# Trasa VIE↔PVK lieta len Pi/So/Po → realistické presné dĺžky pobytu
STAY_PRESETS = [
    {"label": "7 nocí", "min_nights": 7, "max_nights": 7},
    {"label": "9 nocí", "min_nights": 9, "max_nights": 9},
    {"label": "10 nocí", "min_nights": 10, "max_nights": 10},
]
# predvolený rozsah (prvý preset) — pre prípadné iné použitie (napr. alert)
MIN_NIGHTS = STAY_PRESETS[0]["min_nights"]
MAX_NIGHTS = STAY_PRESETS[0]["max_nights"]

# Reálny náklad: počet osôb + fixné doplnky (batožina + miestenky)
PERSONS = 2
BAGGAGE_PER_LEG_EUR = 23.89          # jeden kufor nad hlavu, účtovaný na každý let
SEATS_EUR = 20.0                     # miestenky (spolu za booking)
EXTRAS_EUR = BAGGAGE_PER_LEG_EUR * 2 + SEATS_EUR   # = 67.78 (kufor tam+späť + miestenky)

# Defaultne počítame LEN letenky (bez batožiny/miesteniek). Na True zapne extras do odhadu.
INCLUDE_EXTRAS = False

# Telegram alert: pošli keď najlacnejšia letenka/os (naprieč STAY_PRESETS) klesne na
# nové minimum A zároveň je ≤ ALERT_TARGET_EUR. Creds idú cez env (GitHub Secrets).
ALERT_TARGET_EUR = 130.0
REPORT_URL = "https://hujco.github.io/flight-tracker/"
# chat id nie je tajné (bez tokenu sa s ním nedá nič) → môže byť tu; token ostáva v Secrets
TELEGRAM_CHAT_ID = "8804095194"

# Referencia spred 2 rokov: celá suma za 2 osoby vrátane batožiny a miesteniek
REFERENCE_PRICE_EUR = 301.0
# Odvodená čistá letenka na osobu vtedy: (301 − extras) / osoby ≈ 116.61
REFERENCE_PER_PERSON_EUR = round((REFERENCE_PRICE_EUR - EXTRAS_EUR) / PERSONS, 2)

# OUT = tam (origin->destinacia), RET = spat (destinacia->origin)
ORIGIN = "VIE"
DESTINATIONS = [
    {"code": "PVK", "label": "Lefkada"},    # letisko Preveza/Aktion
]

# Druhé odletisko: Budapešť (BUD). Na rozdiel od VIE (sken celého mesiaca naprieč
# dĺžkami pobytu) tu sledujeme LEN striktné fixné itineráre s pevnou dĺžkou pobytu.
# Lieta na tie isté ostrovné kódy ako VIE → v DB ich rozlišuje stĺpec `origin`.
BUD_ORIGIN = "BUD"
BUD_DESTINATIONS = [
    {"code": "PVK", "label": "Lefkada"},
    # Kefalonia (EFL): Ryanair z Budapešti NElieta (0 letov za sept 2026 pri overení).
    # Ak pribudne, stačí odkomentovať:
    # {"code": "EFL", "label": "Kefalonia"},
]
# Každý trip = presný odlet + presný návrat. Pridať/odobrať = jeden riadok.
BUD_TRIPS = [
    {"out": "2026-09-06", "ret": "2026-09-13"},   # 7 nocí
    {"out": "2026-09-01", "ret": "2026-09-08"},   # 7 nocí (voliteľné)
]

# Náš hlavný let: zvýrazní sa navrchu reportu (fixný termín, ktorý reálne riešime).
PRIMARY_TRIP = {"origin": "BUD", "destination": "PVK",
                "out": "2026-09-06", "ret": "2026-09-13"}


def _trip_nights(trip):
    return (date.fromisoformat(trip["ret"]) - date.fromisoformat(trip["out"])).days


# Preset(y) dĺžky pobytu pre BUD odvodené z fixných itinerárov (tu všetky 7 nocí).
BUD_STAY_PRESETS = [
    {"label": f"{n} nocí", "min_nights": n, "max_nights": n}
    for n in sorted({_trip_nights(t) for t in BUD_TRIPS})
]

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "prices.db"
REPORT_PATH = ROOT / "report.html"
LOG_PATH = ROOT / "flight-tracker.log"
