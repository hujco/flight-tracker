"""Telegram alert pri novom cenovom minime pod cieľom.

Stav netreba držať zvlášť — celá história je v SQLite, takže „nové minimum"
sa počíta porovnaním aktuálneho merania voči všetkým predošlým.
"""
import os
from collections import defaultdict
from datetime import date

import requests

from . import config, stats

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
    if price <= reference_per_person:
        head = "🔥 Skvelá cena (ako pred 2 rokmi!)"
    else:
        head = "✅ Dobrá cena"
    lines = [
        f"<b>{head} — {origin_code}↔{destination_label}</b>",
        f"Letenka {origin_code}↔{destination_label}: <b>{price:.0f} €/os</b> ({c['label']})",
        f"{_fmt_date(c['out_date'])} → {_fmt_date(c['ret_date'])} · {c['nights']} nocí",
    ]
    if info["prev_low"] is not None:
        lines.append(f"Predošlé minimum: {info['prev_low']:.0f} €/os")
    lines.append(f"Cieľ: ≤ {target:.0f} €/os")
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


def maybe_notify(rows, session=None):
    """Alert LEN pre náš let (config.PRIMARY_TRIP): nové minimum pod cieľom → Telegram.

    Sledujeme jediný fixný termín, takže upozorňujeme výhradne naň — nikdy nie na
    lacný iný dátum (to bola presne tá mätúca vec, ktorú nechceme).
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.TELEGRAM_CHAT_ID
    trip = config.PRIMARY_TRIP
    info = detect_primary_trip_low(rows, trip, config.ALERT_TARGET_EUR, config.ORIGIN)
    if info is None:
        return False, "žiadne nové minimum pod cieľom"
    dest_label = _dest_label(trip["destination"])
    tag = f"{trip['origin']}↔{dest_label}"
    if not token or not chat_id:
        return False, f"{tag}: nové min {info['price']:.0f} €, ale chýba TELEGRAM_TOKEN"
    text = format_message(info, dest_label, trip["origin"],
                          config.REFERENCE_PER_PERSON_EUR,
                          config.ALERT_TARGET_EUR, config.REPORT_URL)
    send_telegram(token, chat_id, text, session=session)
    return True, f"{tag}: poslaný alert {info['price']:.0f} €/os"


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
