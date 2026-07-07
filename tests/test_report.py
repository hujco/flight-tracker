from tracker import report

# Sledujeme len Lefkadu (PVK). VIE = sken mesiaca, tu jedna 7-nocová kombinácia.
ROWS = [
    {"observed_at": "2026-06-30T14:00", "origin": "VIE", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR1", "price": 40.0},
    {"observed_at": "2026-06-30T14:00", "origin": "VIE", "destination": "PVK", "direction": "RET", "flight_date": "2026-10-03", "flight_number": "FR2", "price": 70.0},  # 7 noci -> 110
]


def test_report_lefkada_no_destination_toggle():
    html = report.build_report_html(ROWS)
    assert "<html" in html.lower()
    assert "Lefkada" in html
    # jedina destinacia -> ziadny prepinac destinacii (button sa nerenderuje)
    assert "class='dest-btn'" not in html
    assert "Destinácia:" not in html
    assert "Kefalonia" not in html and "Zakyntos" not in html
    assert "110" in html                      # VIE 40+70 round-trip (7 noci)
    assert "VIE→PVK" in html                  # panel pouziva vlastny label


def test_report_shows_origins_side_by_side():
    # Lefkada ma VIE aj BUD data -> dva stlpce vedla seba (origin-grid)
    rows = ROWS + [
        {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-06", "flight_number": "W6A", "price": 20.0},
        {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "RET", "flight_date": "2026-09-13", "flight_number": "W6B", "price": 25.0},  # 7 noci -> 45
    ]
    html = report.build_report_html(rows)
    assert "origin-grid" in html              # vedla seba
    assert "(VIE)" in html and "(BUD)" in html
    assert "BUD→PVK" in html                  # BUD stlpec ma vlastny label
    assert "45" in html                       # BUD 20+25 round-trip (7 noci)


def test_report_empty():
    assert "Zatiaľ žiadne dáta" in report.build_report_html([])


def test_write_report_creates_file(tmp_path):
    out = tmp_path / "report.html"
    report.write_report(ROWS, out)
    assert out.exists() and "Lefkada" in out.read_text(encoding="utf-8")
