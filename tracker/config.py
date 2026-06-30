from pathlib import Path

YEAR = 2026
MONTH = 9
CURRENCY = "EUR"

# Dĺžka pobytu pre round-trip: prepínateľné presety (počet nocí, vrátane hraníc)
# Trasa VIE↔EFL lieta len Pi/So/Po → realistické presné dĺžky pobytu
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

# OUT = tam (VIE->EFL), RET = spat (EFL->VIE)
LEGS = [
    {"direction": "OUT", "origin": "VIE", "destination": "EFL"},
    {"direction": "RET", "origin": "EFL", "destination": "VIE"},
]

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "prices.db"
REPORT_PATH = ROOT / "report.html"
LOG_PATH = ROOT / "flight-tracker.log"
