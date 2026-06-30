from collections import defaultdict


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


def cheapest_roundtrip_now(rows, max_results=10):
    ts = latest_observed_at(rows)
    if ts is None:
        return []
    out = [r for r in rows if r["observed_at"] == ts and r["direction"] == "OUT"]
    ret = [r for r in rows if r["observed_at"] == ts and r["direction"] == "RET"]
    combos = []
    for o in out:
        for b in ret:
            if b["flight_date"] >= o["flight_date"]:  # navrat nie pred odletom
                combos.append(
                    {
                        "out_date": o["flight_date"],
                        "out_price": o["price"],
                        "ret_date": b["flight_date"],
                        "ret_price": b["price"],
                        "total": round(o["price"] + b["price"], 2),
                    }
                )
    combos.sort(key=lambda c: c["total"])
    return combos[:max_results]


def cheapest_roundtrip_over_time(rows):
    by_ts = defaultdict(list)
    for r in rows:
        by_ts[r["observed_at"]].append(r)
    series = []
    for ts in sorted(by_ts):
        best = cheapest_roundtrip_now(by_ts[ts], max_results=1)
        if best:
            series.append((ts, best[0]["total"]))
    return series
