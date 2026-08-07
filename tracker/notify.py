"""Telegram alert pri novom cenovom minime pod cieľom.

Stav netreba držať zvlášť — celá história je v SQLite, takže „nové minimum"
sa počíta porovnaním aktuálneho merania voči všetkým predošlým.
"""
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import requests

from . import config, db, stats

_API = "https://api.telegram.org/bot{token}/sendMessage"


def _fmt_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def cheapest_per_observation(rows, presets):
    """Pre každé meranie vráti najlacnejšiu round-trip kombináciu naprieč presetmi.

    Návrat: {observed_at: combo_dict_with_label} (combo má kľúče z
    stats.cheapest_roundtrip_now + 'label').
    """
    by_ts = defaultdict(list)
    for r in rows:
        by_ts[r["observed_at"]].append(r)
    result = {}
    for ts, rws in by_ts.items():
        best = None
        for p in presets:
            combos = stats.cheapest_roundtrip_now(
                rws, min_nights=p["min_nights"], max_nights=p["max_nights"])
            if combos and (best is None or combos[0]["total"] < best["total"]):
                best = {**combos[0], "label": p["label"]}
        if best is not None:
            result[ts] = best
    return result


def _dest_label(code):
    for lst in (config.DESTINATIONS, getattr(config, "BUD_DESTINATIONS", [])):
        for d in lst:
            if d["code"] == code:
                return d["label"]
    return code


def detect_primary_trip_low(rows, trip, target, default_origin=None):
    """Nové cenové minimum PRE NÁŠ let (fixný termín), alebo None.

    Sleduje výhradne trip["out"]/trip["ret"] daného odletiska — nikdy najlacnejšiu
    kombináciu naprieč mesiacom, aby alert neposlal cenu iného dátumu.
    """
    series = stats.primary_trip_over_time(rows, trip, default_origin)
    if not series:
        return None
    latest = series[-1]
    price = latest["total"]
    if price > target:
        return None
    prev = [s["total"] for s in series[:-1]]
    if prev and price >= min(prev):
        return None  # nie je striktne nové minimum
    nights = (date.fromisoformat(trip["ret"]) - date.fromisoformat(trip["out"])).days
    return {
        "price": price,
        "observed_at": latest["observed_at"],
        "combo": {"out_date": trip["out"], "ret_date": trip["ret"],
                  "nights": nights, "label": f"{nights} nocí"},
        "prev_low": min(prev) if prev else None,
    }


def _combo(trip):
    nights = (date.fromisoformat(trip["ret"]) - date.fromisoformat(trip["out"])).days
    return {"out_date": trip["out"], "ret_date": trip["ret"],
            "nights": nights, "label": f"{nights} nocí"}


def detect_target(series, target):
    """Cena je ≤ cieľ. Urgentné — pri tejto cene sa kupuje, bez ohľadu na minulosť."""
    if not series:
        return None
    latest = series[-1]
    if latest["total"] > target:
        return None
    prev = [s["total"] for s in series[:-1]]
    return {"kind": "target", "price": latest["total"],
            "observed_at": latest["observed_at"],
            "prev_low": min(prev) if prev else None,
            "all_time_low": not prev or latest["total"] < min(prev)}


def detect_window_low(series, days):
    """Najnižšie za posledných `days` dní — BEZ cenového stropu.

    Toto je oprava pôvodnej logiky: podmienka „absolútne minimum A ZÁROVEŇ ≤ cieľ"
    sa po zásahu historického minima zamkla natrvalo a alert prestal chodiť.
    Lokálne minimum je použiteľný nákupný signál aj keď je nad cieľom.
    """
    win = stats.window_series(series, days)
    if len(win) < 2:
        return None
    latest = win[-1]
    prev = [s["total"] for s in win[:-1]]
    if latest["total"] >= min(prev):
        return None
    return {"kind": "window_low", "price": latest["total"],
            "observed_at": latest["observed_at"], "prev_low": min(prev),
            "window_days": days}


def detect_spike(series, hours, pct):
    """Cena vyskočila o ≥ `pct` oproti minimu za posledných `hours` hodín.

    Mesiac pred odletom je dominantné riziko opačné než pokles — že cena utečie.
    Bez tohto signálu systém principiálne nevie povedať „kupuj teraz".
    """
    win = stats.window_series(series, hours / 24.0)
    if len(win) < 2:
        return None
    latest = win[-1]
    prev = [s["total"] for s in win[:-1]]
    low = min(prev)
    if low <= 0 or latest["total"] < low * (1 + pct):
        return None
    return {"kind": "spike", "price": latest["total"],
            "observed_at": latest["observed_at"], "prev_low": low,
            "change_pct": round(100.0 * (latest["total"] - low) / low, 1),
            "window_hours": hours}


def detect_signals(rows, trip, target=None, default_origin=None, today=None):
    """Všetky aktívne signály pre náš let, zoradené od najurgentnejšieho.

    Poradie je zámerné: `target` je priama výzva kúpiť, `window_low` príležitosť,
    `spike` varovanie. Posiela sa len prvý, ktorý prejde cooldownom.
    """
    target = target if target is not None else config.ALERT_TARGET_EUR
    series = stats.primary_trip_over_time(rows, trip, default_origin)
    if not series:
        return []
    days_left = stats.days_until(trip["out"], today)
    # blízko odletu skracujeme okno — čakať sa už nedá, každý prepad ráta
    window = (config.ALERT_WINDOW_DAYS_NEAR
              if days_left <= config.NEAR_DEPARTURE_DAYS
              else config.ALERT_WINDOW_DAYS)
    found = [
        detect_target(series, target),
        detect_window_low(series, window),
        detect_spike(series, config.ALERT_SPIKE_HOURS, config.ALERT_SPIKE_PCT),
    ]
    combo = _combo(trip)
    return [{**s, "combo": combo, "days_left": days_left} for s in found if s]


def detect_new_low(rows, presets, target):
    """Vráti info o novom minime pod cieľom, alebo None.

    Nové minimum = cena posledného merania je STRIKTNE nižšia než najnižšia
    spomedzi všetkých predošlých meraní, a zároveň ≤ target.
    """
    per = cheapest_per_observation(rows, presets)
    if not per:
        return None
    latest_ts = max(per)
    combo = per[latest_ts]
    price = combo["total"]
    if price > target:
        return None
    prev = [c["total"] for ts, c in per.items() if ts != latest_ts]
    if prev and price >= min(prev):
        return None  # nie je striktne nové minimum
    return {
        "price": price,
        "observed_at": latest_ts,
        "combo": combo,
        "prev_low": min(prev) if prev else None,
    }


def format_message(info, destination_label, origin_code, reference_per_person, target, report_url):
    c = info["combo"]
    price = info["price"]
    kind = info.get("kind", "target")
    if kind == "spike":
        head = "📈 Cena stúpa — okno sa zatvára"
    elif kind == "window_low":
        head = f"📉 Najnižšie za {info.get('window_days')} dní"
    elif price <= reference_per_person:
        head = "🔥 Skvelá cena (ako pred 2 rokmi!)"
    else:
        head = "✅ Dobrá cena"
    lines = [
        f"<b>{head} — {origin_code}↔{destination_label}</b>",
        f"Letenka {origin_code}↔{destination_label}: <b>{price:.0f} €/os</b> ({c['label']})",
        f"{_fmt_date(c['out_date'])} → {_fmt_date(c['ret_date'])} · {c['nights']} nocí",
    ]
    if kind == "spike":
        lines.append(f"Za {info.get('window_hours')} h +{info.get('change_pct')} % "
                     f"(z {info['prev_low']:.0f} €/os)")
        lines.append("Ak si videl lacnejšie a váhal, teraz je posledná šanca.")
    elif info.get("prev_low") is not None:
        lines.append(f"Predošlé minimum: {info['prev_low']:.0f} €/os")
    if kind != "spike":
        lines.append(f"Cieľ: ≤ {target:.0f} €/os")
    days_left = info.get("days_left")
    if days_left is not None and days_left >= 0:
        lines.append(f"⏳ Do odletu {days_left} dní")
    if kind != "spike":
        # Minimum = najlacnejší fare bucket → typicky len pár voľných miest.
        lines.append(f"⚠️ {config.SEATS_HINT}")
    lines.append(report_url)
    return "\n".join(lines)


def send_telegram(token, chat_id, text, session=None):
    client = session or requests
    resp = client.post(
        _API.format(token=token),
        data={"chat_id": chat_id, "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": "true"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def _on_cooldown(conn, kind, now_iso):
    """Rovnaký druh signálu sa neopakuje skôr než po ALERT_COOLDOWN_HOURS.

    Stav je v tabuľke `alerts` — bez conn (napr. v testoch) cooldown neplatí.
    """
    if conn is None:
        return False
    hours = config.ALERT_COOLDOWN_HOURS.get(kind)
    if not hours:
        return False
    last = db.last_alert(conn, kind)
    if not last:
        return False
    try:
        prev = datetime.fromisoformat(last["sent_at"])
        now = datetime.fromisoformat(now_iso)
    except (TypeError, ValueError):
        return False
    return (now - prev) < timedelta(hours=hours)


def maybe_notify(rows, session=None, conn=None, now=None):
    """Alert LEN pre náš let (config.PRIMARY_TRIP) → Telegram.

    Sledujeme jediný fixný termín, takže upozorňujeme výhradne naň — nikdy nie na
    lacný iný dátum (to bola presne tá mätúca vec, ktorú nechceme).

    Signálov je viac (target / window_low / spike) a sú nezávislé; pošle sa prvý,
    ktorý prejde cooldownom, aby jedno meranie nikdy neposlalo dve správy.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.TELEGRAM_CHAT_ID
    trip = config.PRIMARY_TRIP
    now_iso = now or datetime.now(timezone.utc).isoformat(timespec="minutes")
    signals = detect_signals(rows, trip, config.ALERT_TARGET_EUR, config.ORIGIN)
    if not signals:
        return False, "žiadny aktívny signál"
    dest_label = _dest_label(trip["destination"])
    tag = f"{trip['origin']}↔{dest_label}"
    info = next((s for s in signals if not _on_cooldown(conn, s["kind"], now_iso)), None)
    if info is None:
        kinds = ", ".join(s["kind"] for s in signals)
        return False, f"{tag}: signály ({kinds}) v cooldowne"
    if not token or not chat_id:
        return False, (f"{tag}: signál {info['kind']} @ {info['price']:.0f} €, "
                       "ale chýba TELEGRAM_TOKEN")
    text = format_message(info, dest_label, trip["origin"],
                          config.REFERENCE_PER_PERSON_EUR,
                          config.ALERT_TARGET_EUR, config.REPORT_URL)
    send_telegram(token, chat_id, text, session=session)
    if conn is not None:
        db.record_alert(conn, now_iso, info["kind"], info["price"], info["observed_at"])
    return True, f"{tag}: poslaný alert {info['kind']} {info['price']:.0f} €/os"


def send_test(session=None):
    """Pošli skúšobnú správu (na overenie že Telegram funguje)."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False, "chýba TELEGRAM_TOKEN"
    send_telegram(token, chat_id,
                  "✅ Test: Flight tracker alert funguje.\n" + config.REPORT_URL,
                  session=session)
    return True, "testovací alert poslaný"
