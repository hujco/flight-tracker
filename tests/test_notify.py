from tracker import notify

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
    # Nas let je nad cielom (140) -> ziadny alert (toto bola stara chyba: 130 < 155)
    rows = [
        _row("t1", "PVK", "OUT", "2026-09-06", 80.0, origin="BUD"), _row("t1", "PVK", "RET", "2026-09-13", 75.0, origin="BUD"),  # 155 > 140
    ]
    s = _CaptureSession()
    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    ok, msg = notify.maybe_notify(rows, session=s)
    assert ok is False and len(s.sent) == 0
