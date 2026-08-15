from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _nights_between(out_date, ret_date):
    return (date.fromisoformat(ret_date) - date.fromisoformat(out_date)).days


LOCAL_TZ = "Europe/Bratislava"


def to_local(value):
    """ISO reťazec alebo datetime -> aware datetime v našom pásme.

    Zber beží v UTC, ale všetko, čo číta človek (report, čas ranného súhrnu),
    má byť v jeho čase. Naivné hodnoty sú staré riadky — tie boli písané v UTC.
    """
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.astimezone(ZoneInfo(LOCAL_TZ))
    except Exception:      # chýbajúca tz databáza → aspoň korektné UTC
        return dt.astimezone(timezone.utc)


def parse_ts(value):
    """observed_at -> naivný UTC datetime, alebo None.

    V DB sú OBA tvary: riadky spred prechodu na UTC sú naivné ('2026-08-07T02:27'),
    novšie majú offset ('2026-08-07T05:27+00:00'). Priame porovnanie tých dvoch
    hodí TypeError, tak všetko normalizujeme na naivné UTC. Staré riadky boli
    reálne písané v UTC (GitHub Actions), takže sa nič neposúva.
    """
    try:
        ts = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


_parse_ts = parse_ts   # spätná kompatibilita pre interné volania


def window_series(series, days, key="observed_at"):
    """Chvost série za posledných `days` dní, meraných od POSLEDNÉHO merania.

    Zámerne nie od „teraz" — keď zber vypadne, okno sa má počítať voči dátam,
    ktoré reálne máme, nie voči nástennému času.

    Keď sa timestampy nedajú parsovať, vráti celú sériu: okno sa nedá vymedziť,
    tak radšej porovnávame voči všetkému (prísnejšie) než by sme mali spadnúť.
    """
    if not series:
        return []
    end = _parse_ts(series[-1][key])
    if end is None:
        return list(series)
    start = end - timedelta(days=days)
    out = []
    for s in series:
        ts = _parse_ts(s[key])
        if ts is None or ts >= start:
            out.append(s)
    return out


def days_until(iso_date, today=None):
    """Dní do daného dátumu (záporné = už bolo)."""
    today = today or date.today()
    return (date.fromisoformat(iso_date) - today).days


def percentile_of(values, value):
    """Podiel hodnôt STRIKTNE nižších než `value`, v percentách.

    0 % = najlacnejšie, čo sme kedy videli; 100 % = najdrahšie.
    """
    if not values:
        return None
    lower = sum(1 for v in values if v < value)
    return round(100.0 * lower / len(values), 1)


def total_with_extras(base_total, persons, extras):
    """Reálny náklad: základ za 1 os. × počet osôb + fixné doplnky (batožina, miestenky)."""
    return round(base_total * persons + extras, 2)


def measurements_label(n):
    """1 meranie / 2 merania / 5 meraní — číslo v zlom tvare zdržuje pri čítaní."""
    if n == 1:
        return "1 meranie"
    if 2 <= n <= 4:
        return f"{n} merania"
    return f"{n} meraní"


def latest_observed_at(rows):
    return max((r["observed_at"] for r in rows), default=None)


def cheapest_leg_over_time(rows, direction):
    """Najnižšia cena danej nohy pri každom meraní: [(observed_at, min_price), ...]."""
    by_ts = defaultdict(list)
    for r in rows:
        if r["direction"] == direction:
            by_ts[r["observed_at"]].append(r["price"])
    return [(ts, min(by_ts[ts])) for ts in sorted(by_ts)]


def price_series(rows, direction):
    series = defaultdict(list)
    for r in sorted(rows, key=lambda x: x["observed_at"]):
        if r["direction"] == direction:
            series[r["flight_date"]].append((r["observed_at"], r["price"]))
    return dict(series)


def cheapest_roundtrip_now(rows, max_results=10, min_nights=0, max_nights=None):
    ts = latest_observed_at(rows)
    if ts is None:
        return []
    # OUT a RET párujeme LEN v rámci rovnakého odletiska (origin) — inak by sa
    # spároval napr. odlet z BUD s návratom do VIE. Riadky bez originu (staré
    # dáta) tvoria jednu skupinu, takže správanie ostáva spätne kompatibilné.
    out_by_origin = defaultdict(list)
    ret_by_origin = defaultdict(list)
    for r in rows:
        if r["observed_at"] != ts:
            continue
        if r["direction"] == "OUT":
            out_by_origin[r.get("origin")].append(r)
        elif r["direction"] == "RET":
            ret_by_origin[r.get("origin")].append(r)
    combos = []
    for origin, out in out_by_origin.items():
        for o in out:
            for b in ret_by_origin.get(origin, []):
                nights = _nights_between(o["flight_date"], b["flight_date"])
                if nights < min_nights:
                    continue
                if max_nights is not None and nights > max_nights:
                    continue
                combos.append(
                    {
                        "out_date": o["flight_date"],
                        "out_price": o["price"],
                        "ret_date": b["flight_date"],
                        "ret_price": b["price"],
                        "nights": nights,
                        "total": round(o["price"] + b["price"], 2),
                    }
                )
    combos.sort(key=lambda c: c["total"])
    return combos[:max_results]


def primary_trip_over_time(rows, trip, default_origin=None):
    """Cena JEDNÉHO fixného letu (origin+dest + presné out/ret dni) pri každom meraní.

    Zámerne nepáruje naprieč mesiacom (to robí cheapest_roundtrip_now) — vracia
    striktne náš termín, aby hore/alert nikdy neukázali cenu iného dátumu.
    Návrat: [{observed_at, out_price, ret_price, total}, ...] zoradené v čase.
    """
    legs = defaultdict(lambda: {"OUT": [], "RET": []})
    for r in rows:
        origin = r.get("origin") or default_origin
        if origin != trip["origin"] or r.get("destination") != trip["destination"]:
            continue
        if r["direction"] == "OUT" and r["flight_date"] == trip["out"]:
            legs[r["observed_at"]]["OUT"].append(r["price"])
        elif r["direction"] == "RET" and r["flight_date"] == trip["ret"]:
            legs[r["observed_at"]]["RET"].append(r["price"])
    series = []
    for ts in sorted(legs):
        out, ret = legs[ts]["OUT"], legs[ts]["RET"]
        if out and ret:
            op, rp = min(out), min(ret)
            series.append({"observed_at": ts, "out_price": op, "ret_price": rp,
                           "total": round(op + rp, 2)})
    return series


def leg_over_time(rows, trip, direction, default_origin=None):
    """Cena JEDNEJ nohy nášho letu v čase: [{observed_at, price}, ...].

    Súčet oboch nôh vie zakryť, že jedna z nich je na minime — návrat tvorí
    ~80 % sumy, takže jeho pohyb prehluší lacný odlet. Preto sledujeme aj nohy
    zvlášť (jednosmerné letenky sa dajú kúpiť samostatne).
    """
    flight_date = trip["out"] if direction == "OUT" else trip["ret"]
    by_ts = {}
    for r in rows:
        origin = r.get("origin") or default_origin
        if origin != trip["origin"] or r.get("destination") != trip["destination"]:
            continue
        if r["direction"] != direction or r["flight_date"] != flight_date:
            continue
        ts, price = r["observed_at"], r["price"]
        if ts not in by_ts or price < by_ts[ts]:
            by_ts[ts] = price
    return [{"observed_at": ts, "price": by_ts[ts]} for ts in sorted(by_ts)]


def decision_series(rows, trip, default_origin=None, out_bought=False):
    """Séria, podľa ktorej sa reálne rozhodujeme — jeden zdroj pravdy pre report aj alerty.

    Kým nie je nič kúpené, je to súčet oboch nôh. Keď je odlet kúpený, miešal by
    súčet cenu, ktorú už ovplyvniť nemôžeme, s tou, ktorú áno — vtedy je
    rozhodovacou veličinou samotný návrat.
    Kľúč ostáva "total", nech naň sedia všetci existujúci konzumenti.
    """
    if out_bought:
        return [{"observed_at": x["observed_at"], "total": x["price"]}
                for x in leg_over_time(rows, trip, "RET", default_origin)]
    return primary_trip_over_time(rows, trip, default_origin)


def option_series(rows, options, default_origin=None, out_bought=False):
    """Rozhodovacia séria pre KAŽDÝ zvažovaný termín, od najlacnejšieho.

    Termíny sa zámerne nezlievajú do jednej „najlacnejšej" série: nový dátum
    začína bez histórie, takže spoločná séria by rozdiel medzi dvoma rôznymi
    letmi (179 → 101 €) čítala ako prepad ceny. Každý termín má vlastnú históriu.

    Termín bez dát vypadne — objaví sa až keď ho zber prvýkrát chytí.
    Návrat: [{trip, series, price, observed_at}, ...] zoradené od najlacnejšieho.
    """
    snaps = []
    for trip in options:
        series = decision_series(rows, trip, default_origin, out_bought)
        if not series:
            continue
        snaps.append({"trip": trip, "series": series,
                      "price": series[-1]["total"],
                      "observed_at": series[-1]["observed_at"]})
    snaps.sort(key=lambda s: s["price"])
    return snaps


def cheapest_roundtrip_over_time(rows, min_nights=0, max_nights=None):
    by_ts = defaultdict(list)
    for r in rows:
        by_ts[r["observed_at"]].append(r)
    series = []
    for ts in sorted(by_ts):
        best = cheapest_roundtrip_now(
            by_ts[ts], max_results=1, min_nights=min_nights, max_nights=max_nights)
        if best:
            series.append((ts, best[0]["total"]))
    return series
