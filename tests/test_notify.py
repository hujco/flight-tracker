from datetime import date

from tracker import notify, stats

PRESETS = [
    {"label": "7 nocí", "min_nights": 7, "max_nights": 7},
    {"label": "9 nocí", "min_nights": 9, "max_nights": 9},
]


def _obs(ts, out_d, out_p, ret_d, ret_p):
    return [
        {"observed_at": ts, "direction": "OUT", "flight_date": out_d, "flight_number": "FRo", "price": out_p},
        {"observed_at": ts, "direction": "RET", "flight_date": ret_d, "flight_number": "FRr", "price": ret_p},
    ]


def test_detect_new_low_fires_below_target_and_new_min():
    rows = []
    rows += _obs("t1", "2026-09-07", 60.0, "2026-09-14", 60.0)   # 7 noci, total 120
    rows += _obs("t2", "2026-09-07", 50.0, "2026-09-14", 55.0)   # 7 noci, total 105 (nove min, < 130)
    info = notify.detect_new_low(rows, PRESETS, target=130)
    assert info is not None
    assert info["price"] == 105.0
    assert info["prev_low"] == 120.0
    assert info["combo"]["nights"] == 7


def test_detect_new_low_none_when_above_target():
    rows = _obs("t1", "2026-09-07", 100.0, "2026-09-14", 100.0)  # 200 > 130
    assert notify.detect_new_low(rows, PRESETS, target=130) is None


def test_detect_new_low_none_when_not_strictly_lower():
    rows = []
    rows += _obs("t1", "2026-09-07", 50.0, "2026-09-14", 55.0)   # 105
    rows += _obs("t2", "2026-09-07", 50.0, "2026-09-14", 55.0)   # 105 (rovnake, nie nizsie)
    assert notify.detect_new_low(rows, PRESETS, target=130) is None


def test_detect_new_low_first_observation_below_target_fires():
    rows = _obs("t1", "2026-09-07", 50.0, "2026-09-14", 55.0)    # 105, ziadna historia
    info = notify.detect_new_low(rows, PRESETS, target=130)
    assert info is not None and info["prev_low"] is None


def test_format_message_includes_destination_origin_and_tier():
    info = {"price": 110.0, "observed_at": "t1", "prev_low": 130.0,
            "combo": {"out_date": "2026-09-07", "ret_date": "2026-09-14", "nights": 7, "label": "7 nocí"}}
    msg = notify.format_message(info, "Lefkada", "BUD", reference_per_person=117.0, target=130.0, report_url="http://x")
    assert "Lefkada" in msg
    assert "BUD↔Lefkada" in msg           # origin v texte, nie natvrdo VIE
    assert "Skvelá" in msg               # 110 <= 117
    assert "07.09.2026" in msg and "110 €/os" in msg

    msg2 = notify.format_message({**info, "price": 125.0}, "Zakyntos", "VIE", 117.0, 130.0, "http://x")
    assert "VIE↔Zakyntos" in msg2 and "Dobrá cena" in msg2   # 125 > 117


def test_format_message_includes_seat_hint():
    # alert sa posiela len pri novom minime pod cielom = najlacnejsi fare bucket,
    # takze sprava musi upozornit ze moze zostavat len par sedadiel
    info = {"price": 110.0, "observed_at": "t1", "prev_low": 130.0,
            "combo": {"out_date": "2026-09-07", "ret_date": "2026-09-14", "nights": 7, "label": "7 nocí"}}
    msg = notify.format_message(info, "Lefkada", "BUD", reference_per_person=117.0, target=130.0, report_url="http://x")
    assert "len pár sedadiel" in msg


class _FakeResp:
    def __init__(self):
        self.payload = {"ok": True}
    def raise_for_status(self):
        pass
    def json(self):
        return self.payload


class _FakeSession:
    def __init__(self):
        self.calls = []
    def post(self, url, data=None, timeout=None):
        self.calls.append((url, data))
        return _FakeResp()


def test_send_telegram_posts_to_api():
    s = _FakeSession()
    out = notify.send_telegram("TOK", "CHAT", "ahoj", session=s)
    assert out == {"ok": True}
    url, data = s.calls[0]
    assert "botTOK/sendMessage" in url
    assert data["chat_id"] == "CHAT"
    assert data["text"] == "ahoj"


def _row(ts, dest, direction, fdate, price, origin="VIE"):
    return {"observed_at": ts, "origin": origin, "destination": dest, "direction": direction,
            "flight_date": fdate, "flight_number": "FR", "price": price}


class _CaptureSession:
    def __init__(self):
        self.sent = []
    def post(self, url, data=None, timeout=None):
        self.sent.append(data["text"])
        class R:
            def raise_for_status(self_): pass
            def json(self_): return {"ok": True}
        return R()


def test_maybe_notify_fires_for_our_trip(monkeypatch):
    # Nas let (BUD 6->13.9) klesne na nove minimum pod cielom (<140) -> alert
    rows = [
        _row("t1", "PVK", "OUT", "2026-09-06", 80.0, origin="BUD"), _row("t1", "PVK", "RET", "2026-09-13", 80.0, origin="BUD"),  # 160 > 140
        _row("t2", "PVK", "OUT", "2026-09-06", 60.0, origin="BUD"), _row("t2", "PVK", "RET", "2026-09-13", 65.0, origin="BUD"),  # 125 (nove min < 140)
    ]
    s = _CaptureSession()
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    ok, msg = notify.maybe_notify(rows, session=s)
    assert ok is True
    assert len(s.sent) == 1
    assert "BUD↔Lefkada" in s.sent[0] and "125 €/os" in s.sent[0]


def test_maybe_notify_only_our_date_not_cheaper_other_date(monkeypatch):
    # Iny datum (1->8) je lacnejsi, ale alert musi ist LEN podla nasho terminu (6->13).
    rows = [
        _row("t1", "PVK", "OUT", "2026-09-01", 20.0, origin="BUD"), _row("t1", "PVK", "RET", "2026-09-08", 20.0, origin="BUD"),  # iny termin 40
        _row("t1", "PVK", "OUT", "2026-09-06", 60.0, origin="BUD"), _row("t1", "PVK", "RET", "2026-09-13", 65.0, origin="BUD"),  # nas termin 125 < 140
    ]
    s = _CaptureSession()
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    ok, msg = notify.maybe_notify(rows, session=s)
    assert ok is True and len(s.sent) == 1
    assert "125 €/os" in s.sent[0]        # nas termin, nie 40 z ineho datumu
    assert "06.09.2026" in s.sent[0] and "13.09.2026" in s.sent[0]
    # alt-datum (1->8) sa nesmie objavit v sprave
    assert "01.09.2026" not in s.sent[0] and "08.09.2026" not in s.sent[0]


def test_maybe_notify_ignores_other_origin(monkeypatch):
    # VIE lacna na nasich datumoch, ale nas let je z BUD -> VIE nesmie spustit alert.
    rows = [
        _row("t1", "PVK", "OUT", "2026-09-06", 30.0, origin="VIE"), _row("t1", "PVK", "RET", "2026-09-13", 30.0, origin="VIE"),  # VIE 60, nie nas let
    ]
    s = _CaptureSession()
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    ok, msg = notify.maybe_notify(rows, session=s)
    assert ok is False and len(s.sent) == 0


def test_maybe_notify_none_above_target(monkeypatch):
    # Jedine meranie nad cielom -> ziadny signal (na window_low/spike treba
    # aspon dve merania). Cena je odvodena od configu, nech test neprestane
    # davat zmysel pri zmene ALERT_TARGET_EUR.
    above = notify.config.ALERT_TARGET_EUR + 100
    rows = [
        _row("t1", "PVK", "OUT", "2026-09-06", above / 2, origin="BUD"),
        _row("t1", "PVK", "RET", "2026-09-13", above / 2, origin="BUD"),
    ]
    s = _CaptureSession()
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    ok, msg = notify.maybe_notify(rows, session=s)
    assert ok is False and len(s.sent) == 0


# --- nezavisle signaly (target / window_low / spike) ---------------------------

def _series(*pairs):
    """[(observed_at, total), ...] -> tvar, aky vracia stats.primary_trip_over_time."""
    return [{"observed_at": ts, "total": total} for ts, total in pairs]


def test_window_low_fires_above_target_when_locally_cheapest():
    # Jadro opravy: 150 je nad cielom (140), ale je to najnizsie za okno -> alert.
    # Stara logika (absolutne minimum A ZAROVEN <= ciel) by nesposlala nic.
    s = _series(("2026-08-01T06:00", 200.0), ("2026-08-05T06:00", 180.0),
                ("2026-08-06T06:00", 150.0))
    info = notify.detect_window_low(s, days=14)
    assert info is not None
    assert info["price"] == 150.0 and info["prev_low"] == 180.0


def test_window_low_ignores_older_minimum_outside_window():
    # 126 spred 30 dni uz do 14-dnoveho okna nespada -> 150 je stale lokalne minimum.
    # Presne toto zamklo povodny alert natrvalo.
    s = _series(("2026-07-05T06:00", 126.0), ("2026-08-05T06:00", 180.0),
                ("2026-08-06T06:00", 150.0))
    assert notify.detect_window_low(s, days=14) is not None
    assert notify.detect_window_low(s, days=60) is None   # v sirsom okne uz nie


def test_signals_survive_mixed_naive_and_aware_timestamps():
    # Regresia: prechod na UTC spravil nove observed_at aware ('...+00:00'), kym
    # 5 tyzdnov historie je naivnych. Porovnanie hodilo TypeError a notify ticho
    # umrel (run.py ho chyta) -> alerty nefungovali vobec.
    s = _series(("2026-08-01T06:00", 200.0),                # stary, naivny
                ("2026-08-06T06:00", 180.0),
                ("2026-08-07T05:27+00:00", 150.0))          # novy, aware
    assert notify.detect_window_low(s, days=14) is not None
    assert notify.detect_spike(s, hours=24, pct=0.08) is None
    assert stats.window_series(s, 14)                        # nepadne


def test_parse_ts_normalizes_both_shapes():
    naive = stats.parse_ts("2026-08-07T05:27")
    aware = stats.parse_ts("2026-08-07T05:27+00:00")
    assert naive == aware and aware.tzinfo is None
    assert stats.parse_ts("t1") is None                      # fiktivny ts -> None


def test_window_low_needs_strictly_lower():
    s = _series(("2026-08-05T06:00", 150.0), ("2026-08-06T06:00", 150.0))
    assert notify.detect_window_low(s, days=14) is None


def test_spike_fires_on_jump():
    s = _series(("2026-08-06T00:00", 126.0), ("2026-08-06T12:00", 198.0))
    info = notify.detect_spike(s, hours=24, pct=0.08)
    assert info is not None
    assert info["prev_low"] == 126.0 and info["change_pct"] == 57.1


def test_spike_ignores_small_move_and_drop():
    flat = _series(("2026-08-06T00:00", 150.0), ("2026-08-06T12:00", 154.0))  # +2.7 %
    assert notify.detect_spike(flat, hours=24, pct=0.08) is None
    down = _series(("2026-08-06T00:00", 200.0), ("2026-08-06T12:00", 150.0))
    assert notify.detect_spike(down, hours=24, pct=0.08) is None


def test_spike_only_looks_inside_window():
    # lacne meranie je 5 dni stare -> do 24h okna nespada, ziadny spike
    s = _series(("2026-08-01T06:00", 126.0), ("2026-08-06T06:00", 198.0))
    assert notify.detect_spike(s, hours=24, pct=0.08) is None


def test_target_fires_regardless_of_all_time_low():
    # 135 nie je absolutne minimum (126), ale je pod cielom -> stale sa kupuje
    s = _series(("2026-07-13T14:00", 126.0), ("2026-08-06T06:00", 135.0))
    info = notify.detect_target(s, target=140)
    assert info is not None and info["all_time_low"] is False


def test_signals_priority_target_before_window_low():
    rows = [
        _row("2026-08-01T06:00", "PVK", "OUT", "2026-09-06", 100.0, origin="BUD"),
        _row("2026-08-01T06:00", "PVK", "RET", "2026-09-13", 100.0, origin="BUD"),  # 200
        _row("2026-08-06T06:00", "PVK", "OUT", "2026-09-06", 60.0, origin="BUD"),
        _row("2026-08-06T06:00", "PVK", "RET", "2026-09-13", 65.0, origin="BUD"),   # 125
    ]
    kinds = [s["kind"] for s in notify.detect_signals(rows, notify.config.PRIMARY_TRIP)]
    assert kinds[0] == "target" and "window_low" in kinds


def test_maybe_notify_cooldown_blocks_repeat_of_same_kind(monkeypatch):
    import sqlite3
    from tracker import db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    rows = [
        _row("2026-08-01T06:00", "PVK", "OUT", "2026-09-06", 100.0, origin="BUD"),
        _row("2026-08-01T06:00", "PVK", "RET", "2026-09-13", 100.0, origin="BUD"),
        _row("2026-08-06T06:00", "PVK", "OUT", "2026-09-06", 60.0, origin="BUD"),
        _row("2026-08-06T06:00", "PVK", "RET", "2026-09-13", 65.0, origin="BUD"),   # 125
    ]
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    s = _CaptureSession()
    ok, _ = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-06T06:05")
    assert ok is True and len(s.sent) == 1

    # o hodinu neskor: target je v cooldowne -> padne sa na window_low, nie ticho
    ok2, msg2 = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-06T07:05")
    assert ok2 is True and "window_low" in msg2

    # oba uz odoslane -> tretie volanie mlci
    ok3, msg3 = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-06T08:05")
    assert ok3 is False and "cooldowne" in msg3
    assert len(s.sent) == 2


def test_digest_sent_when_nothing_fired_for_a_day(monkeypatch):
    import sqlite3
    from tracker import db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    high = notify.config.ALERT_TARGET_EUR + 100
    rows = [
        _row("2026-08-01T06:00", "PVK", "OUT", "2026-09-06", high / 2, origin="BUD"),
        _row("2026-08-01T06:00", "PVK", "RET", "2026-09-13", high / 2, origin="BUD"),
        _row("2026-08-07T06:00", "PVK", "OUT", "2026-09-06", high / 2, origin="BUD"),
        _row("2026-08-07T06:00", "PVK", "RET", "2026-09-13", high / 2, origin="BUD"),
    ]
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    s = _CaptureSession()
    # ziadny signal (cena plocha a nad cielom), zaroven nikdy nic neposlane -> suhrn
    ok, msg = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-07T06:05")
    assert ok is True and "digest" in msg
    assert "Denný súhrn" in s.sent[0]

    # o hodinu neskor uz nie (heartbeat je 24 h)
    ok2, _ = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-07T07:05")
    assert ok2 is False and len(s.sent) == 1

    # o 25 h zase ano
    ok3, _ = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-08T07:05")
    assert ok3 is True and len(s.sent) == 2


def test_digest_not_sent_without_conn(monkeypatch):
    # bez DB sa stav nedá sledovať -> heartbeat by posielal pri kazdom behu
    high = notify.config.ALERT_TARGET_EUR + 100
    rows = [
        _row("2026-08-01T06:00", "PVK", "OUT", "2026-09-06", high / 2, origin="BUD"),
        _row("2026-08-01T06:00", "PVK", "RET", "2026-09-13", high / 2, origin="BUD"),
    ]
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    s = _CaptureSession()
    ok, _ = notify.maybe_notify(rows, session=s)
    assert ok is False and len(s.sent) == 0


def test_digest_message_has_decision_numbers():
    series = _series(("2026-08-01T06:00", 200.0), ("2026-08-06T06:00", 180.0),
                     ("2026-08-07T06:00", 222.0))
    info = notify.build_digest(series, notify.config.PRIMARY_TRIP,
                               today=date(2026, 8, 7))
    msg = notify._format_digest(info, "Lefkada", "BUD", 180.0, "http://x")
    assert "Denný súhrn" in msg and "222 €/os" in msg
    assert "Za 7 dní: 180 – 222" in msg
    # 2 z 3 merani boli lacnejsie -> 67 % (aktualna cena rata do menovatela)
    assert "drahšie než 67 %" in msg
    assert "Do odletu 30 dní" in msg


def test_format_message_spike_says_buy_now():
    info = {"kind": "spike", "price": 198.0, "prev_low": 126.0, "change_pct": 57.1,
            "window_hours": 24, "days_left": 31, "observed_at": "t",
            "combo": {"out_date": "2026-09-06", "ret_date": "2026-09-13",
                      "nights": 7, "label": "7 nocí"}}
    msg = notify.format_message(info, "Lefkada", "BUD", 117.0, 140.0, "http://x")
    assert "Cena stúpa" in msg and "+57.1 %" in msg
    assert "posledná šanca" in msg
    assert "Do odletu 31 dní" in msg
    assert "len pár sedadiel" not in msg      # pri raste je hint o sedadlach nezmysel
