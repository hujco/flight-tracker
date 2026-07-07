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


def test_maybe_notify_per_destination(monkeypatch):
    # EFL klesne na nove minimum pod cielom, ZTH ostava draha
    rows = [
        _row("t1", "EFL", "OUT", "2026-09-07", 70.0), _row("t1", "EFL", "RET", "2026-09-14", 70.0),  # 140
        _row("t2", "EFL", "OUT", "2026-09-07", 50.0), _row("t2", "EFL", "RET", "2026-09-14", 55.0),  # 105 (nove min < 130)
        _row("t2", "ZTH", "OUT", "2026-09-07", 100.0), _row("t2", "ZTH", "RET", "2026-09-14", 100.0),  # 200
    ]
    sent = []

    class S:
        def post(self, url, data=None, timeout=None):
            sent.append(data["text"])
            class R:
                def raise_for_status(self_): pass
                def json(self_): return {"ok": True}
            return R()

    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    ok, msg = notify.maybe_notify(rows, session=S())
    assert ok is True
    assert len(sent) == 1                 # len VIE EFL
    assert "Kefalonia" in sent[0]
    assert "VIE↔Kefalonia" in sent[0]


def test_maybe_notify_separates_origins(monkeypatch):
    # rovnaka destinacia (PVK/Lefkada), ale VIE draha a BUD lacna -> alert len pre BUD
    rows = [
        _row("t1", "PVK", "OUT", "2026-09-06", 100.0, origin="VIE"), _row("t1", "PVK", "RET", "2026-09-13", 100.0, origin="VIE"),  # VIE 200
        _row("t1", "PVK", "OUT", "2026-09-06", 40.0, origin="BUD"),  _row("t1", "PVK", "RET", "2026-09-13", 40.0, origin="BUD"),   # BUD 80 < 130
    ]
    sent = []

    class S:
        def post(self, url, data=None, timeout=None):
            sent.append(data["text"])
            class R:
                def raise_for_status(self_): pass
                def json(self_): return {"ok": True}
            return R()

    monkeypatch.setenv("TELEGRAM_TOKEN", "TOK")
    ok, msg = notify.maybe_notify(rows, session=S())
    assert ok is True
    assert len(sent) == 1
    assert "BUD↔Lefkada" in sent[0]       # BUD, nie VIE; cena 80 (nesparovana s VIE)
    assert "80 €/os" in sent[0]
