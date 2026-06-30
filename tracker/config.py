from pathlib import Path

YEAR = 2026
MONTH = 9
CURRENCY = "EUR"

# Dĺžka pobytu pre round-trip: počet nocí medzi odletom a návratom (vrátane hraníc)
MIN_NIGHTS = 5
MAX_NIGHTS = 10

# Reálny náklad: počet osôb + fixné doplnky (batožina + miestenky)
PERSONS = 2
BAGGAGE_PER_LEG_EUR = 23.89          # jeden kufor nad hlavu, účtovaný na každý let
SEATS_EUR = 20.0                     # miestenky (spolu za booking)
EXTRAS_EUR = BAGGAGE_PER_LEG_EUR * 2 + SEATS_EUR   # = 67.78 (kufor tam+späť + miestenky)

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
