from collections import defaultdict
from datetime import date


def _nights_between(out_date, ret_date):
    return (date.fromisoformat(ret_date) - date.fromisoformat(out_date)).days


def total_with_extras(base_total, persons, extras):
    """Reálny náklad: základ za 1 os. × počet osôb + fixné doplnky (batožina, miestenky)."""
    return round(base_total * persons + extras, 2)


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
