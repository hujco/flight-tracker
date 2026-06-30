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
