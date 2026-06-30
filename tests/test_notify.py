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


def test_format_message_tiers_great_when_below_reference():
    info = {"price": 110.0, "observed_at": "t1", "prev_low": 130.0,
            "combo": {"out_date": "2026-09-07", "ret_date": "2026-09-14", "nights": 7, "label": "7 nocí"}}
    msg = notify.format_message(info, reference_per_person=117.0, target=130.0, report_url="http://x")
    assert "Skvelá" in msg          # 110 <= 117
    assert "07.09.2026" in msg and "14.09.2026" in msg
    assert "110 €/os" in msg


def test_format_message_good_when_above_reference():
    info = {"price": 125.0, "observed_at": "t1", "prev_low": None,
            "combo": {"out_date": "2026-09-07", "ret_date": "2026-09-14", "nights": 7, "label": "7 nocí"}}
    msg = notify.format_message(info, reference_per_person=117.0, target=130.0, report_url="http://x")
    assert "Dobrá cena" in msg       # 125 > 117


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
