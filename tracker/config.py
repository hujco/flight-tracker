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

# Telegram alerty. Creds idú cez env (GitHub Secrets).
#
# Pôvodne bola jediná podmienka „nové ABSOLÚTNE minimum A ZÁROVEŇ ≤ cieľ". Tá sa po
# zásahu historického minima (126.57 € dňa 13.7.) natrvalo zamkla — aj výborná cena
# 135 € by už neposlala nič. Preto sú signály rozbité na nezávislé:
#   target      — cena ≤ ALERT_TARGET_EUR (urgentné, kupuj)
#   window_low  — najnižšie za posledných N dní (aj keď nad cieľom)
#   spike       — cena vyskočila hore, okno sa zatvára
# 140 € bola cena z prvého týždňa sledovania; za posledné 2 týždne pod ňu cena
# neklesla ani raz (medián 197 €), takže alert mlčal. 180 € je „toto beriem"
# hranica pre aktuálnu situáciu — ale sama o sebe je tiež riedka (1 zo 112 meraní
# za 14 dní), preto je pod ňou ešte HEARTBEAT_HOURS súhrn.
ALERT_TARGET_EUR = 180.0

# Ranný súhrn: prvý beh v daný deň od tejto hodiny (NÁŠHO času) pošle prehľad,
# nech je hneď ráno jasné, na akej cene deň začína. Nie presne o 7:00 —
# scheduled workflows na GitHube sa oneskorujú, takže je to „prvý beh po 7:00".
DIGEST_HOUR_LOCAL = 7

# Poistka, keby ranný beh vypadol: keď X hodín neprišlo vôbec nič, pošli súhrn.
# Ticho nikdy nesmie znamenať „asi je to pokazené".
HEARTBEAT_HOURS = 24

# „Najnižšie za posledných N dní". Mesiac pred odletom skracujeme okno — vtedy je
# každý lokálny prepad reálna príležitosť, lebo času na čakanie už niet.
ALERT_WINDOW_DAYS = 14
ALERT_WINDOW_DAYS_NEAR = 10
NEAR_DEPARTURE_DAYS = 30          # od kedy platí skrátené okno

# Spike: rast o ≥ X oproti minimu za posledných N hodín → „ak si videl lacnejšie, ber".
ALERT_SPIKE_PCT = 0.08
ALERT_SPIKE_HOURS = 24

# Aby alerty nespamovali: rovnaký druh signálu najskôr po N hodinách. Keď je signál
# v cooldowne, padá sa na ďalší v poradí — takže nový nižší prepad počas „target"
# cooldownu prejde cez window_low a neutopí sa.
ALERT_COOLDOWN_HOURS = {"target": 12, "window_low": 12, "spike": 48,
                        "ret_low": 12, "out_low": 12}

# Jednotlivé nohy sa dajú kúpiť samostatne a návrat tvorí ~80 % sumy, takže
# jeho pohyb v súčte prehluší lacný odlet. Preto vlastný, kratší window.
ALERT_LEG_WINDOW_DAYS = 10

# ODLET JE KÚPENÝ (10. 8. 2026). Odteraz sa rozhodujeme už len o návrate —
# súčet oboch nôh by miešal cenu, ktorú nemôžeme ovplyvniť, s tou, ktorú áno.
# Hero, verdikt aj alerty preto bežia nad samotným návratom.
OUT_LEG_BOUGHT = True

# Čo sme za odlet reálne zaplatili. Banka stiahla 151 € za 2 osoby (to je presné);
# rozpis bol ~105 $ letenky a ~171 $ spolu, teda kurz 151/171 = 0.883:
#   letenky  105 $ -> 92.72 €  za 2 os. = 46.36 €/os
#   doplnky   66 $ -> 58.28 €  za 2 os. = 29.14 €/os (batožina + fasttrack + miestenky)
# Sledované ceny sú holé letenky, preto sa všade porovnáva 46.36, nie 75.50.
OUT_LEG_PAID_TOTAL_EUR = 151.0        # celá platba za booking (2 os., všetko)
OUT_LEG_PAID_EUR = 46.36              # z toho samotná letenka, na osobu
# Doplnky na osobu a nohu — na návrat ich zaplatíme znova (rovnaký rozsah).
EXTRAS_PER_PERSON_PER_LEG_EUR = 29.14

# Cieľ pre samotný návrat: ALERT_TARGET_EUR (180 za obe letenky/os) − zaplatený
# odlet. Nie je to mŕtve číslo — návrat bol pred 2 týždňami na 130,87 €.
ALERT_TARGET_RET_EUR = round(ALERT_TARGET_EUR - OUT_LEG_PAID_EUR, 2)
REPORT_URL = "https://hujco.github.io/flight-tracker/"
# chat id nie je tajné (bez tokenu sa s ním nedá nič) → môže byť tu; token ostáva v Secrets
TELEGRAM_CHAT_ID = "8804095194"

# Heuristika „málo sedadiel": Ryanair endpoint farfnd nevracia počet voľných miest
# (seats_left ostáva NULL), a availability endpoint blokuje anti-bot. Keď je cena na
# historickom minime, je to najlacnejší fare bucket — ten typicky máva len pár miest.
# Presný počet nevieme, preto varujeme, nech používateľ over a rezervuje hneď.
SEATS_HINT = ("Pri takejto cene u Ryanairu zvyčajne zostáva len pár sedadiel za túto "
              "sumu — over počet a rezervuj hneď na ryanair.com.")

# Prepínač „počet osôb" násobí cenu/os × N, lenže naša cena je lead-in (najlacnejšie
# jedno sedadlo). Ryanair skoro nikdy nemá N miest za tú najnižšiu cenu, takže reálna
# suma za viac osôb býva vyššia (ďalší cestujúci padne do drahšieho fare bucketu).
# farfnd to nevie rozlíšiť (aj s adultPaxCount len násobí), presné číslo dá len
# blokovaný availability endpoint — preto pri prepínači úprimná poznámka.
PERSONS_HINT = ("Suma za viac osôb je orientačná: predpokladá, že toľko miest je za "
                "najnižšiu cenu. Pri málo miestach ďalší cestujúci zaplatí viac — "
                "over reálnu cenu na ryanair.com.")

# Referencia spred 2 rokov: celá suma za 2 osoby vrátane batožiny a miesteniek
REFERENCE_PRICE_EUR = 301.0
# Odvodená čistá letenka na osobu vtedy: (301 − extras) / osoby ≈ 116.61
REFERENCE_PER_PERSON_EUR = round((REFERENCE_PRICE_EUR - EXTRAS_EUR) / PERSONS, 2)

# OUT = tam (origin->destinacia), RET = spat (destinacia->origin)
#
# ORIGIN ostáva "VIE" LEN ako default pre staré riadky v DB, ktoré vznikli pred
# multi-origin a nemajú vyplnený stĺpec `origin`. Aktívne sa z Viedne už nezbiera.
ORIGIN = "VIE"

# Viedeň je vypnutá: ubytovanie na Lefkade je zaplatené na fixný termín 6.9.,
# a VIE↔PVK lieta stredy a soboty — na náš termín (nedeľa) teda neexistuje spoj.
# Porovnávať flexibilnú Viedeň s fixným Budapešťou bolo zavádzajúce.
# Prázdny zoznam = žiadny sken mesiaca, zostáva len fixný BUD itinerár nižšie
# (4 requesty na beh namiesto 62). Historické VIE dáta v `prices.db` ostávajú.
DESTINATIONS = []

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
# O NÁVRATE SA EŠTE ROZHODUJEME. Odlet 6.9. je kúpený a pre obe možnosti rovnaký,
# takže voľba je čisto „ktorý návrat kúpime". PVK→BUD lieta v nedeľu a v utorok,
# preto „o dva dni neskôr" znamená utorok 15.9. (14. ani 16.9. spoj neexistuje).
#
# Dva dni navyše na Lefkade nie sú náklad navyše: do Budapešti ideme až v deň
# odletu, takže odpadne tamojšie ubytovanie. Kým ubytovanie na Lefkade nepotvrdí
# cenu predĺženia, porovnávame holé letenky — pridať náklad za noc navyše by
# znamenalo hádať číslo a tváriť sa, že ho vieme.
#
# Každá možnosť má VLASTNÚ históriu a vlastné signály. Zámerne sa nezlievajú do
# jednej „najlacnejšej" série: 15.9. začína bez histórie, takže spoločná séria by
# skok zo 179 na 101 € čítala ako prepad ceny, hoci je to iný let.
RETURN_OPTIONS = [
    {"origin": "BUD", "destination": "PVK", "out": "2026-09-06", "ret": "2026-09-13"},
    {"origin": "BUD", "destination": "PVK", "out": "2026-09-06", "ret": "2026-09-15"},
]

# Náš hlavný let: fallback pre miesta, kde treba jediný termín (spätná kompatibilita).
# Rozhodovanie beží nad RETURN_OPTIONS — rozhoduje ten, ktorý je práve lacnejší.
PRIMARY_TRIP = RETURN_OPTIONS[0]

# Čo sa reálne zbiera. Odvodené z RETURN_OPTIONS, nech je zdroj pravdy jeden:
# pridanie termínu vyššie automaticky pridá jeho deň do zberu.
BUD_TRIPS = [{"out": t["out"], "ret": t["ret"]} for t in RETURN_OPTIONS]


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
