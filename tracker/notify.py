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


def format_message(info, reference_per_person, target, report_url):
    c = info["combo"]
    price = info["price"]
    if price <= reference_per_person:
        head = "🔥 Skvelá cena (ako pred 2 rokmi!)"
    else:
        head = "✅ Dobrá cena"
    lines = [
        f"<b>{head}</b>",
        f"Letenka VIE↔EFL: <b>{price:.0f} €/os</b> ({c['label']})",
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
    """Pošli Telegram alert, ak je nové minimum pod cieľom a sú nastavené creds.

    Vráti (bool_poslane, sprava_do_logu). Nikdy nevyhodí kvôli chýbajúcim creds.
    """
    info = detect_new_low(rows, config.STAY_PRESETS, config.ALERT_TARGET_EUR)
    if info is None:
        return False, "žiadne nové minimum pod cieľom"
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False, (f"nové minimum {info['price']:.0f} € pod cieľom, ale chýba "
                       "TELEGRAM_TOKEN — alert preskočený")
    text = format_message(
        info, config.REFERENCE_PER_PERSON_EUR, config.ALERT_TARGET_EUR, config.REPORT_URL)
    send_telegram(token, chat_id, text, session=session)
    return True, f"poslaný alert: {info['price']:.0f} €/os"


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
