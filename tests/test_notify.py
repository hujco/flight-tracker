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

    # obe nohy tiez klesli -> dalsie v poradi su ich vlastne signaly
    ok3, msg3 = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-06T08:05")
    assert ok3 is True and "ret_low" in msg3      # navrat prvy, tvori vacsinu sumy
    ok4, msg4 = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-06T09:05")
    assert ok4 is True and "out_low" in msg4

    # vsetky signaly v cooldowne, ale dnes este nebol ranny suhrn -> posle sa
    ok5, msg5 = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-06T10:05")
    assert ok5 is True and "digest" in msg5

    # az teraz ticho: signaly v cooldowne aj suhrn uz dnes bol
    ok6, msg6 = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-06T11:05")
    assert ok6 is False and "cooldowne" in msg6
    assert len(s.sent) == 5


def test_leg_low_fires_when_total_is_high():
    # Realny scenar z 10.8.: sucet 209 € je vysoko (ziadny signal zo suctu),
    # ale odlet je pritom na minime za okno. Podla suctu by neprislo nic.
    rows = []
    for ts, out_p, ret_p in (("2026-08-01T06:00", 50.0, 130.0),
                             ("2026-08-05T06:00", 61.0, 150.0),
                             ("2026-08-10T06:00", 43.0, 166.0)):   # sucet stupol
        rows += [_row(ts, "PVK", "OUT", "2026-09-06", out_p, origin="BUD"),
                 _row(ts, "PVK", "RET", "2026-09-13", ret_p, origin="BUD")]
    kinds = [s["kind"] for s in notify.detect_signals(rows, notify.config.PRIMARY_TRIP)]
    assert "out_low" in kinds          # odlet klesol
    assert "ret_low" not in kinds      # navrat stupol
    assert "window_low" not in kinds   # sucet stupol -> zo suctu nic


def test_leg_low_prefers_return_leg():
    # Navrat tvori ~80 % sumy -> ked klesnu obe, hlas najprv navrat
    rows = []
    for ts, out_p, ret_p in (("2026-08-01T06:00", 60.0, 170.0),
                             ("2026-08-10T06:00", 43.0, 150.0)):
        rows += [_row(ts, "PVK", "OUT", "2026-09-06", out_p, origin="BUD"),
                 _row(ts, "PVK", "RET", "2026-09-13", ret_p, origin="BUD")]
    legs = [s["kind"] for s in
            notify.detect_leg_lows(rows, notify.config.PRIMARY_TRIP, 10)]
    assert legs == ["ret_low", "out_low"]


def test_leg_low_message_says_it_can_be_bought_alone():
    info = {"kind": "ret_low", "direction": "RET", "price": 133.0, "prev_low": 150.0,
            "all_min": 96.0, "pct": 20.0, "window_days": 10, "days_left": 27,
            "observed_at": "t",
            "combo": {"out_date": "2026-09-06", "ret_date": "2026-09-13",
                      "nights": 7, "label": "7 nocí"}}
    msg = notify.format_message(info, "Lefkada", "BUD", 117.0, 180.0, "http://x")
    assert "Návrat je najnižšie za 10 dní" in msg
    assert "Lefkada→BUD 13.09.2026" in msg and "133 €/os" in msg
    assert "historické minimum 96 €" in msg
    assert "Lacnejšie než 80 % histórie" in msg
    assert "samostatne" in msg


def test_signals_run_on_return_only_when_outbound_bought(monkeypatch):
    monkeypatch.setattr(notify.config, "OUT_LEG_BOUGHT", True)
    monkeypatch.setattr(notify.config, "ALERT_TARGET_RET_EUR", 137.0)
    rows = []
    for ts, out_p, ret_p in (("2026-08-01T06:00", 50.0, 160.0),
                             ("2026-08-10T06:00", 60.0, 130.0)):   # sucet klesol len o 20
        rows += [_row(ts, "PVK", "OUT", "2026-09-06", out_p, origin="BUD"),
                 _row(ts, "PVK", "RET", "2026-09-13", ret_p, origin="BUD")]
    sig = notify.detect_signals(rows, notify.config.PRIMARY_TRIP)
    kinds = [s["kind"] for s in sig]
    # navrat 130 <= ciel 137 -> target; a je to jeho minimum -> window_low
    assert kinds[0] == "target"
    assert sig[0]["price"] == 130.0          # cena NAVRATU, nie suctu (190)
    # o kupenom odlete sa uz nehlasi
    assert "out_low" not in kinds and "ret_low" not in kinds


def test_effective_target_follows_bought_state(monkeypatch):
    monkeypatch.setattr(notify.config, "OUT_LEG_BOUGHT", False)
    assert notify.effective_target() == notify.config.ALERT_TARGET_EUR
    monkeypatch.setattr(notify.config, "OUT_LEG_BOUGHT", True)
    monkeypatch.setattr(notify.config, "ALERT_TARGET_RET_EUR", 137.0)
    assert notify.effective_target() == 137.0


def _digest_conn():
    import sqlite3
    from tracker import db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def test_morning_digest_fires_on_first_run_after_seven_local():
    conn = _digest_conn()
    # 04:30 UTC = 06:30 CEST -> este skoro
    assert notify._morning_due(conn, "2026-08-11T04:30+00:00") is False
    # 05:10 UTC = 07:10 CEST -> prvy beh po 7:00
    assert notify._morning_due(conn, "2026-08-11T05:10+00:00") is True


def test_morning_digest_only_once_per_day():
    from tracker import db
    conn = _digest_conn()
    db.record_alert(conn, "2026-08-11T05:10+00:00", "digest", 166.0, "x")
    # neskor v ten isty den uz nie
    assert notify._morning_due(conn, "2026-08-11T09:00+00:00") is False
    assert notify._morning_due(conn, "2026-08-11T19:00+00:00") is False
    # nasledujuce rano zase ano
    assert notify._morning_due(conn, "2026-08-12T05:10+00:00") is True


def test_morning_digest_uses_local_day_not_utc_day():
    from tracker import db
    conn = _digest_conn()
    # 22:30 UTC 11.8. = 00:30 CEST 12.8. -> lokalne uz novy den, ale este pred 7:00
    db.record_alert(conn, "2026-08-11T05:10+00:00", "digest", 166.0, "x")
    assert notify._morning_due(conn, "2026-08-11T22:30+00:00") is False


def test_morning_digest_independent_of_other_alerts():
    from tracker import db
    conn = _digest_conn()
    # spike prisiel o 6:00 CEST; ranny suhrn ma aj tak prist
    db.record_alert(conn, "2026-08-11T04:00+00:00", "spike", 200.0, "x")
    assert notify._morning_due(conn, "2026-08-11T05:10+00:00") is True


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


def test_messages_show_all_in_price_when_extras_known(monkeypatch):
    # Sledujeme holu letenku, ale rozhodujeme sa podla sumy na ucte.
    monkeypatch.setattr(notify.config, "OUT_LEG_BOUGHT", True)
    monkeypatch.setattr(notify.config, "OUT_LEG_PAID_TOTAL_EUR", 151.0)
    monkeypatch.setattr(notify.config, "EXTRAS_PER_PERSON_PER_LEG_EUR", 29.14)
    monkeypatch.setattr(notify.config, "PERSONS", 2)
    lines = notify.all_in_lines(134.0)
    # (134 + 29.14) * 2 = 326; cela cesta 151 + 326 = 477
    assert "326 €" in lines[0] and "2 os." in lines[0]
    assert "477 €" in lines[1] and "151 €" in lines[1]


def test_all_in_lines_silent_when_nothing_bought(monkeypatch):
    monkeypatch.setattr(notify.config, "OUT_LEG_BOUGHT", False)
    assert notify.all_in_lines(134.0) == []


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


# --- dva mozne navraty (13.9. vs 15.9.) --------------------------------------
#
# Odlet je kupeny a pre obe moznosti rovnaky, takze rozhodovanie je "ktory navrat".
# Kazda moznost ma vlastnu historiu: 15.9. zacina od nuly a zlucena seria by skok
# 179 -> 101 citala ako prepad ceny, hoci je to iny let.

_OPT_13 = {"origin": "BUD", "destination": "PVK", "out": "2026-09-06", "ret": "2026-09-13"}
_OPT_15 = {"origin": "BUD", "destination": "PVK", "out": "2026-09-06", "ret": "2026-09-15"}


def _two_options(monkeypatch):
    monkeypatch.setattr(notify.config, "RETURN_OPTIONS", [_OPT_13, _OPT_15])
    monkeypatch.setattr(notify.config, "OUT_LEG_BOUGHT", True)
    monkeypatch.setattr(notify.config, "ALERT_TARGET_RET_EUR", 134.0)


def _both_rets(ts, out_p, ret13, ret15=None):
    rows = [_row(ts, "PVK", "OUT", "2026-09-06", out_p, origin="BUD"),
            _row(ts, "PVK", "RET", "2026-09-13", ret13, origin="BUD")]
    if ret15 is not None:
        rows.append(_row(ts, "PVK", "RET", "2026-09-15", ret15, origin="BUD"))
    return rows


def test_option_snapshots_rank_cheapest_first(monkeypatch):
    _two_options(monkeypatch)
    rows = _both_rets("2026-08-15T06:00", 46.0, 179.0, 101.0)
    snaps = notify.option_snapshots(rows)
    assert [s["trip"]["ret"] for s in snaps] == ["2026-09-15", "2026-09-13"]
    assert snaps[0]["price"] == 101.0


def test_option_without_data_is_skipped(monkeypatch):
    # 15.9. sa este ani raz nezozbieral -> sprava sa musi tvarit ako predtym,
    # nie spadnut ani hlasit termin bez ceny
    _two_options(monkeypatch)
    rows = _both_rets("2026-08-15T06:00", 46.0, 179.0)
    snaps = notify.option_snapshots(rows)
    assert [s["trip"]["ret"] for s in snaps] == ["2026-09-13"]


def test_signals_are_computed_per_return_date(monkeypatch):
    # 13.9. stupa (ziadny nakupny signal), 15.9. je pod cielom -> target na 15.9.
    _two_options(monkeypatch)
    rows = (_both_rets("2026-08-13T06:00", 46.0, 160.0, 130.0)
            + _both_rets("2026-08-15T06:00", 46.0, 179.0, 101.0))
    snaps = notify.option_snapshots(rows)
    by_ret = {s["trip"]["ret"]: [x["kind"] for x in s["signals"]] for s in snaps}
    assert by_ret["2026-09-15"][0] == "target"     # 101 <= 134
    assert "target" not in by_ret["2026-09-13"]    # 179 je vysoko nad cielom
    assert "window_low" not in by_ret["2026-09-13"]  # a este aj stupol


def test_cheaper_option_alerts_first(monkeypatch):
    _two_options(monkeypatch)
    rows = (_both_rets("2026-08-13T06:00", 46.0, 160.0, 130.0)
            + _both_rets("2026-08-15T06:00", 46.0, 179.0, 101.0))
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    s = _CaptureSession()
    ok, msg = notify.maybe_notify(rows, session=s, now="2026-08-15T06:05")
    assert ok is True and "15.09.2026" in s.sent[0]
    assert "101 €/os" in s.sent[0]


def test_message_names_the_other_return_option(monkeypatch):
    # Rozhodujeme sa MEDZI terminmi -> sprava musi povedat, co je ta druha moznost
    _two_options(monkeypatch)
    rows = (_both_rets("2026-08-13T06:00", 46.0, 160.0, 130.0)
            + _both_rets("2026-08-15T06:00", 46.0, 179.0, 101.0))
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    s = _CaptureSession()
    notify.maybe_notify(rows, session=s, now="2026-08-15T06:05")
    text = s.sent[0]
    assert "13.09.2026" in text and "179 €/os" in text
    assert "78 €/os" in text                     # rozdiel na osobu
    assert f"{78 * notify.config.PERSONS:.0f} €" in text   # a co to robi s penazenkou


def test_cooldown_is_per_return_date(monkeypatch):
    # Alert na jeden termin nesmie umlcat alert na druhy — su to nezavisle nakupy.
    import sqlite3
    from tracker import db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    _two_options(monkeypatch)
    rows = (_both_rets("2026-08-13T06:00", 46.0, 160.0, 130.0)
            + _both_rets("2026-08-15T06:00", 46.0, 133.0, 101.0))   # obe pod cielom
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    s = _CaptureSession()
    ok1, msg1 = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-15T06:05")
    assert ok1 is True and "2026-09-15" in msg1        # lacnejsi ide prvy
    ok2, msg2 = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-15T06:35")
    assert ok2 is True and "2026-09-15" not in msg2    # ten uz je v cooldowne
    assert "2026-09-13" in msg2 and "133 €/os" in s.sent[1]


def test_digest_covers_both_return_options(monkeypatch):
    import sqlite3
    from tracker import db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    _two_options(monkeypatch)
    # obe vysoko nad cielom a ploche -> ziadny signal, posle sa ranny suhrn
    rows = (_both_rets("2026-08-14T06:00", 46.0, 200.0, 180.0)
            + _both_rets("2026-08-15T05:10", 46.0, 200.0, 180.0))
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    s = _CaptureSession()
    ok, msg = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-15T05:10+00:00")
    assert ok is True and "digest" in msg
    text = s.sent[0]
    assert "Denný súhrn" in text
    assert "15.09.2026" in text and "180 €/os" in text     # lacnejsi ako hlavny
    assert "13.09.2026" in text and "200 €/os" in text     # druhy ako porovnanie
    # jedna sprava, nie jedna na termin
    assert len(s.sent) == 1


def test_digest_alert_kind_stays_plain_digest(monkeypatch):
    # _morning_due hlada kind == "digest" -> nesmie sa mu prilepit datum,
    # inak by ranny suhrn chodil kazdy beh
    import sqlite3
    from tracker import db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    _two_options(monkeypatch)
    rows = (_both_rets("2026-08-14T06:00", 46.0, 200.0, 180.0)
            + _both_rets("2026-08-15T05:10", 46.0, 200.0, 180.0))
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    s = _CaptureSession()
    notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-15T05:10+00:00")
    assert db.last_alert(conn, "digest") is not None
    ok2, _ = notify.maybe_notify(rows, session=s, conn=conn, now="2026-08-15T09:00+00:00")
    assert ok2 is False and len(s.sent) == 1


def test_digest_does_not_fake_statistics_for_a_fresh_option(monkeypatch):
    # Novy termin ma jedine meranie: "lacnejsie nez 0 % z 1 merani" a "za 7 dni
    # 101 - 101" nie su cisla, ale sum. Povedz rovno, ze historia sa este zbiera.
    _two_options(monkeypatch)
    snaps = notify.option_snapshots(
        _both_rets("2026-08-15T06:00", 46.0, 179.0, 101.0))
    info = notify.build_digest_multi(snaps, today=date(2026, 8, 15))
    msg = notify._format_digest(info, "Lefkada", "BUD", 134.0, "http://x")
    assert "Zbieram históriu (1 meranie)" in msg
    assert "0 %" not in msg and "Za 7 dní" not in msg
    assert "101 €/os" in msg and "179 €/os" in msg     # ceny naopak chybat nesmu


def test_digest_keeps_statistics_once_history_exists(monkeypatch):
    _two_options(monkeypatch)
    rows = (_both_rets("2026-08-13T06:00", 46.0, 160.0, 130.0)
            + _both_rets("2026-08-15T06:00", 46.0, 179.0, 101.0))
    snaps = notify.option_snapshots(rows)
    info = notify.build_digest_multi(snaps, today=date(2026, 8, 15))
    msg = notify._format_digest(info, "Lefkada", "BUD", 134.0, "http://x")
    assert "Za 7 dní: 101 – 130" in msg and "Zbieram históriu" not in msg
