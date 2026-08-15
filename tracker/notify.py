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


def _nights(trip):
    return (date.fromisoformat(trip["ret"]) - date.fromisoformat(trip["out"])).days


def _combo(trip):
    nights = _nights(trip)
    return {"out_date": trip["out"], "ret_date": trip["ret"],
            "nights": nights, "label": f"{nights} nocí"}


def return_options():
    """Termíny, medzi ktorými sa ešte rozhodujeme (odlet je pre všetky rovnaký)."""
    return list(getattr(config, "RETURN_OPTIONS", None) or [config.PRIMARY_TRIP])


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


def detect_window_low(series, days, key="total", kind="window_low"):
    """Najnižšie za posledných `days` dní — BEZ cenového stropu.

    Toto je oprava pôvodnej logiky: podmienka „absolútne minimum A ZÁROVEŇ ≤ cieľ"
    sa po zásahu historického minima zamkla natrvalo a alert prestal chodiť.
    Lokálne minimum je použiteľný nákupný signál aj keď je nad cieľom.
    """
    win = stats.window_series(series, days)
    if len(win) < 2:
        return None
    latest = win[-1]
    prev = [s[key] for s in win[:-1]]
    if latest[key] >= min(prev):
        return None
    return {"kind": kind, "price": latest[key],
            "observed_at": latest["observed_at"], "prev_low": min(prev),
            "window_days": days}


def detect_leg_lows(rows, trip, days, default_origin=None):
    """Lokálne minimum jednotlivých nôh — signál, ktorý súčet nevie zachytiť.

    Príklad z reálnych dát (10.8.): súčet 209 € bol vysoko, ale odlet bol pritom
    na 14-dňovom minime (42,99 €). Podľa súčtu by neprišlo nič.
    """
    found = []
    for direction in ("RET", "OUT"):   # návrat prvý — tvorí ~80 % sumy
        series = stats.leg_over_time(rows, trip, direction, default_origin)
        info = detect_window_low(series, days, key="price",
                                 kind=f"{direction.lower()}_low")
        if info:
            all_prices = [s["price"] for s in series]
            found.append({**info, "direction": direction,
                          "all_min": min(all_prices),
                          "pct": stats.percentile_of(all_prices, info["price"])})
    return found


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


def build_digest(series, trip, today=None):
    """Pravidelný súhrn — pošle sa, aj keď žiadny signál nevystrelil.

    Bez neho je „všetko beží, cena je len vysoko" a „tracker je pokazený" pre
    používateľa ten istý zážitok: nulové správy.
    """
    if not series:
        return None
    latest = series[-1]
    price = latest["total"]
    week = [x["total"] for x in stats.window_series(series, 7)]
    day = stats.window_series(series, 1)
    prev24 = day[0]["total"] if len(day) > 1 else None
    return {
        "kind": "digest",
        "price": price,
        "observed_at": latest["observed_at"],
        "week_min": min(week),
        "week_max": max(week),
        "all_min": min(x["total"] for x in series),
        "pct": stats.percentile_of([x["total"] for x in series], price),
        "change_24h": (round(100.0 * (price - prev24) / prev24, 1)
                       if prev24 else None),
        "measurements": len(series),
        "combo": _combo(trip),
        "days_left": stats.days_until(trip["out"], today),
    }


def detect_signals(rows, trip, target=None, default_origin=None, today=None):
    """Všetky aktívne signály pre náš let, zoradené od najurgentnejšieho.

    Poradie je zámerné: `target` je priama výzva kúpiť, `window_low` príležitosť,
    `spike` varovanie. Posiela sa len prvý, ktorý prejde cooldownom.
    """
    out_bought = getattr(config, "OUT_LEG_BOUGHT", False)
    if target is None:
        target = (config.ALERT_TARGET_RET_EUR if out_bought
                  else config.ALERT_TARGET_EUR)
    series = stats.decision_series(rows, trip, default_origin, out_bought)
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
        # nohy pred spike: sú to nákupné príležitosti, spike je len varovanie.
        # Keď je odlet kúpený, rozhodovacou sériou UŽ JE návrat, takže by to
        # bol ten istý signál dvakrát — a o kúpenom odlete hlásiť netreba.
        *([] if out_bought
          else detect_leg_lows(rows, trip, config.ALERT_LEG_WINDOW_DAYS, default_origin)),
        detect_spike(series, config.ALERT_SPIKE_HOURS, config.ALERT_SPIKE_PCT),
    ]
    combo = _combo(trip)
    return [{**s, "combo": combo, "days_left": days_left} for s in found if s]


def option_snapshots(rows, options=None, target=None, default_origin=None, today=None):
    """Stav každého zvažovaného návratu, zoradený od najlacnejšieho.

    Každý termín má VLASTNÚ sériu aj vlastné signály. Zlúčiť ich do jednej
    „najlacnejšej" série by z rozdielu medzi dvoma rôznymi letmi urobilo cenový
    pohyb — pri termíne bez histórie by prvé meranie vyzeralo ako prepad ceny.

    Termín bez dát vypadne: nový dátum sa objaví až keď ho zber prvýkrát chytí.
    """
    options = options if options is not None else return_options()
    target = target if target is not None else effective_target()
    default_origin = default_origin if default_origin is not None else config.ORIGIN
    out_bought = getattr(config, "OUT_LEG_BOUGHT", False)
    snaps = stats.option_series(rows, options, default_origin, out_bought)
    return [{**s, "signals": detect_signals(rows, s["trip"], target,
                                            default_origin, today)}
            for s in snaps]


# Poradie naprieč termínmi: najprv urgentnosť signálu, až potom „ktorý je lacnejší".
# Inak by „príležitosť" na lacnejšom termíne predbehla „kupuj" na tom druhom —
# a práve „kupuj" je jediný signál, ktorý pýta okamžitú akciu.
_KIND_PRIORITY = ("target", "window_low", "ret_low", "out_low", "spike")


def _signal_rank(kind):
    return _KIND_PRIORITY.index(kind) if kind in _KIND_PRIORITY else len(_KIND_PRIORITY)


def _alt_info(snaps, index):
    """Najlepšia z ostatných možností — bez nej je cena jedného termínu bezcenná."""
    others = [s for i, s in enumerate(snaps) if i != index]
    if not others:
        return None
    best = others[0]        # snaps sú zoradené od najlacnejšieho
    return {"ret": best["trip"]["ret"], "price": best["price"],
            "nights": _nights(best["trip"])}


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


def _format_leg_low(info, destination_label, origin_code, report_url):
    c = info["combo"]
    out_leg = info["direction"] == "OUT"
    who = "Odlet" if out_leg else "Návrat"
    route = (f"{origin_code}→{destination_label}" if out_leg
             else f"{destination_label}→{origin_code}")
    day = c["out_date"] if out_leg else c["ret_date"]
    lines = [
        f"<b>📉 {who} je najnižšie za {info['window_days']} dní</b>",
        f"{route} {_fmt_date(day)}: <b>{info['price']:.0f} €/os</b>",
        f"Predtým v okne najmenej: {info['prev_low']:.0f} € · "
        f"historické minimum {info['all_min']:.0f} €",
    ]
    lines += _alt_lines(info)
    if info.get("pct") is not None:
        lines.append(f"Lacnejšie než {100 - info['pct']:.0f} % histórie tejto nohy")
    days_left = info.get("days_left")
    if days_left is not None and days_left >= 0:
        lines.append(f"⏳ Do odletu {days_left} dní")
    # jednosmerné letenky sa dajú kúpiť samostatne — o tom celý tento signál je
    lines.append("Túto nohu vieš kúpiť samostatne, bez druhej.")
    lines.append(report_url)
    return "\n".join(lines)


def all_in_lines(fare_per_person):
    """Čo reálne zaplatíme pri danej cene letenky — doplnky sú známe a fixné.

    Sledovaná cena je holá letenka, ale rozhodujeme sa podľa sumy na účte.
    Bez tohto sa porovnávala letenka s referenciou, ktorá doplnky obsahovala.
    """
    if not getattr(config, "OUT_LEG_BOUGHT", False):
        return []
    extras = getattr(config, "EXTRAS_PER_PERSON_PER_LEG_EUR", 0.0)
    paid = getattr(config, "OUT_LEG_PAID_TOTAL_EUR", None)
    if not extras or paid is None:
        return []
    ret_all_in = (fare_per_person + extras) * config.PERSONS
    return [
        f"S doplnkami: <b>{ret_all_in:.0f} €</b> za {config.PERSONS} os. "
        f"(+{extras:.0f} €/os batožina, fasttrack, miestenky)",
        f"Celá cesta: <b>{paid + ret_all_in:.0f} €</b> "
        f"(odlet {paid:.0f} € už zaplatený · pred 2 r. {config.REFERENCE_PRICE_EUR:.0f} €)",
    ]


def _alt_line(ret, nights, alt_price, price):
    """Druhá možnosť v jednom riadku — rozhodujeme sa MEDZI termínmi.

    Bez nej správa hovorí „101 € je dobrá cena", ale zamlčí, že druhý termín je
    o 78 €/os inde. Rozdiel preto uvádzame aj za celú partiu — tam sa rozhoduje.
    """
    diff = alt_price - price
    line = (f"Druhá možnosť — návrat {_fmt_date(ret)} ({nights} nocí): "
            f"<b>{alt_price:.0f} €/os</b>")
    if abs(diff) >= 0.5:
        word = "drahší" if diff > 0 else "lacnejší"
        line += (f" · o {abs(diff):.0f} €/os {word} "
                 f"({abs(diff) * config.PERSONS:.0f} € za {config.PERSONS} os.)")
    return line


def _alt_lines(info):
    alt = info.get("alt")
    if not alt:
        return []
    return [_alt_line(alt["ret"], alt["nights"], alt["price"], info["price"])]


def build_digest_multi(snaps, today=None):
    """Jeden súhrn za všetky zvažované termíny; hlavný je ten práve lacnejší.

    Zámerne nie správa na termín: rozhodujeme sa medzi nimi, takže patria vedľa
    seba — rozdiel má byť vidieť bez prepínania medzi správami.
    """
    pairs = [(s, build_digest(s["series"], s["trip"], today)) for s in snaps]
    pairs = [(s, i) for s, i in pairs if i]
    if not pairs:
        return None
    main_snap, main = pairs[0]
    alts = [{"ret": s["trip"]["ret"], "nights": _nights(s["trip"]), "price": i["price"]}
            for s, i in pairs[1:]]
    return {**main, "trip": main_snap["trip"], "alts": alts}


def _format_digest(info, destination_label, origin_code, target, report_url):
    c = info["combo"]
    price = info["price"]
    pct = info.get("pct")
    measurements = info.get("measurements", 0)
    lines = [
        f"<b>📊 Denný súhrn — {origin_code}↔{destination_label}</b>",
        f"{_fmt_date(c['out_date'])} → {_fmt_date(c['ret_date'])} · {c['nights']} nocí",
        f"Teraz: <b>{price:.0f} €/os</b> "
        f"(spolu {config.PERSONS} os.: {price * config.PERSONS:.0f} €)",
    ]
    if measurements < 2:
        # „lacnejšie než 0 % z 1 merania" a „za 7 dní 101 – 101" nie sú čísla,
        # ale šum: nový termín históriu ešte nemá a treba to povedať rovno.
        lines.append(f"Zbieram históriu ({stats.measurements_label(measurements)}) — "
                     f"porovnanie voči histórii príde po ďalších behoch")
    else:
        lines.append(f"Za 7 dní: {info['week_min']:.0f} – {info['week_max']:.0f} €/os")
        if info.get("change_24h") is not None:
            arrow = ("▲" if info["change_24h"] > 0
                     else ("▼" if info["change_24h"] < 0 else "▬"))
            lines.append(f"Za 24 h: {arrow} {info['change_24h']:+.1f} %")
        if pct is not None:
            # 0 % = najlacnejšie, čo sme videli; 100 % = najdrahšie
            verdict = "drahšie" if pct >= 50 else "lacnejšie"
            lines.append(f"Je to {verdict} než {pct:.0f} % z "
                         f"{stats.measurements_label(measurements)} "
                         f"(minimum {info['all_min']:.0f} €)")
    for a in info.get("alts", []):
        lines.append(_alt_line(a["ret"], a["nights"], a["price"], price))
    lines += all_in_lines(price)
    lines.append(f"Cieľ: ≤ {target:.0f} €/os")
    days_left = info.get("days_left")
    if days_left is not None and days_left >= 0:
        lines.append(f"⏳ Do odletu {days_left} dní")
    lines.append(report_url)
    return "\n".join(lines)


def format_message(info, destination_label, origin_code, reference_per_person, target, report_url):
    c = info["combo"]
    price = info["price"]
    kind = info.get("kind", "target")
    if kind == "digest":
        return _format_digest(info, destination_label, origin_code, target, report_url)
    if kind in ("out_low", "ret_low"):
        return _format_leg_low(info, destination_label, origin_code, report_url)
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
    lines += _alt_lines(info)
    if kind == "spike":
        lines.append(f"Za {info.get('window_hours')} h +{info.get('change_pct')} % "
                     f"(z {info['prev_low']:.0f} €/os)")
        lines.append("Ak si videl lacnejšie a váhal, teraz je posledná šanca.")
    elif info.get("prev_low") is not None:
        lines.append(f"Predošlé minimum: {info['prev_low']:.0f} €/os")
    if kind != "spike":
        # pri nákupnom signáli chce človek vidieť sumu, ktorú reálne zaplatí
        lines += all_in_lines(price)
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


def _cooldown_key(kind, trip):
    """Cooldown je per termín: alert na 15.9. nesmie umlčať alert na 13.9.

    Sú to nezávislé nákupy — kúpiť sa dá len jeden z nich, ale kým je rozhodnutie
    otvorené, musíme vidieť pohyb na oboch.
    """
    return f"{kind}@{trip['ret']}" if trip else kind


def _on_cooldown(conn, kind, now_iso, key=None):
    """Rovnaký druh signálu sa neopakuje skôr než po ALERT_COOLDOWN_HOURS.

    `kind` určuje dĺžku cooldownu, `key` to, čoho sa týka (druh + termín).
    Stav je v tabuľke `alerts` — bez conn (napr. v testoch) cooldown neplatí.
    """
    if conn is None:
        return False
    hours = config.ALERT_COOLDOWN_HOURS.get(kind)
    if not hours:
        return False
    last = db.last_alert(conn, key or kind)
    if not last:
        return False
    prev = stats.parse_ts(last["sent_at"])      # normalizuje naivné aj aware tvary
    now = stats.parse_ts(now_iso)
    if prev is None or now is None:
        return False
    return (now - prev) < timedelta(hours=hours)


def effective_target():
    """Cieľ platný pre to, o čom sa ešte rozhodujeme (celý let vs. samotný návrat)."""
    if getattr(config, "OUT_LEG_BOUGHT", False):
        return config.ALERT_TARGET_RET_EUR
    return config.ALERT_TARGET_EUR


def _morning_due(conn, now_iso):
    """Prvý beh v daný deň po DIGEST_HOUR_LOCAL (v našom čase).

    Zámerne nie „presne o 7:00": cron na GitHube behá nepravidelne a občas beh
    vynechá, takže sa viažeme na prvý beh po tej hodine, nie na konkrétny čas.
    """
    now_local = stats.to_local(now_iso)
    if now_local.hour < config.DIGEST_HOUR_LOCAL:
        return False
    last = db.last_alert(conn, "digest")
    if last is None:
        return True
    return stats.to_local(last["sent_at"]).date() < now_local.date()


def _heartbeat_due(conn, now_iso):
    """Poistka: od POSLEDNÉHO alertu (akéhokoľvek druhu) ubehlo HEARTBEAT_HOURS."""
    last = db.last_alert_any(conn)
    now = stats.parse_ts(now_iso)
    if last is None or now is None:
        return True
    prev = stats.parse_ts(last["sent_at"])
    if prev is None:
        return True
    return (now - prev) >= timedelta(hours=config.HEARTBEAT_HOURS)


def _due_digest(snaps, conn, now_iso):
    """Ranný súhrn, prípadne heartbeat, keď ranný beh vypadol.

    Bez conn sa stav nedá sledovať, tak sa neposiela vôbec — inak by každý beh
    bez signálu poslal správu.
    """
    if conn is None:
        return None
    if not (_morning_due(conn, now_iso) or _heartbeat_due(conn, now_iso)):
        return None
    return build_digest_multi(snaps)


def maybe_notify(rows, session=None, conn=None, now=None):
    """Alert LEN pre termíny, o ktorých sa rozhodujeme (config.RETURN_OPTIONS) → Telegram.

    Nikdy nie lacný iný dátum z mesačného skenu — to bola presne tá mätúca vec,
    ktorú nechceme. Sledované termíny sú ale dva (návrat 13.9. alebo 15.9.),
    takže signály sa počítajú pre každý zvlášť a **slovo dostane prvý ten
    lacnejší** — o ňom sa reálne rozhoduje.

    Signálov je viac (target / window_low / spike) a sú nezávislé; pošle sa prvý,
    ktorý prejde cooldownom, aby jedno meranie nikdy neposlalo dve správy.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.TELEGRAM_CHAT_ID
    now_iso = now or datetime.now(timezone.utc).isoformat(timespec="minutes")
    snaps = option_snapshots(rows)
    trip = snaps[0]["trip"] if snaps else config.PRIMARY_TRIP
    dest_label = _dest_label(trip["destination"])
    tag = f"{trip['origin']}↔{dest_label}"

    candidates = []
    for i, snap in enumerate(snaps):
        alt = _alt_info(snaps, i)
        for sig in snap["signals"]:
            candidates.append({**sig, "trip": snap["trip"], "alt": alt,
                               "key": _cooldown_key(sig["kind"], snap["trip"]),
                               "rank": (_signal_rank(sig["kind"]), i)})
    candidates.sort(key=lambda c: c["rank"])
    info = next((c for c in candidates
                 if not _on_cooldown(conn, c["kind"], now_iso, c["key"])), None)
    if info is None:
        # Nič nevystrelilo (alebo je všetko v cooldowne) → keď už dlho neprišlo nič,
        # pošli aspoň súhrn. Ticho sa inak nedá odlíšiť od poruchy.
        info = _due_digest(snaps, conn, now_iso)
    if info is None:
        if not candidates:
            return False, "žiadny aktívny signál"
        kinds = ", ".join(c["key"] for c in candidates)
        return False, f"{tag}: signály ({kinds}) v cooldowne"
    trip = info.get("trip", trip)
    dest_label = _dest_label(trip["destination"])
    key = info.get("key", info["kind"])
    if not token or not chat_id:
        return False, (f"{tag}: signál {key} @ {info['price']:.0f} €, "
                       "ale chýba TELEGRAM_TOKEN")
    text = format_message(info, dest_label, trip["origin"],
                          config.REFERENCE_PER_PERSON_EUR,
                          effective_target(), config.REPORT_URL)
    send_telegram(token, chat_id, text, session=session)
    if conn is not None:
        db.record_alert(conn, now_iso, key, info["price"], info["observed_at"])
    return True, f"{tag}: poslaný alert {key} {info['price']:.0f} €/os"


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
