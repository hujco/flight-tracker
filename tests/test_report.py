from tracker import report

ROWS = [
    {"observed_at": "2026-06-30T14:00", "destination": "EFL", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR1", "price": 35.0},
    {"observed_at": "2026-06-30T14:00", "destination": "EFL", "direction": "RET", "flight_date": "2026-10-03", "flight_number": "FR2", "price": 98.0},  # 7 noci
    {"observed_at": "2026-06-30T14:00", "destination": "ZTH", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR3", "price": 30.0},
    {"observed_at": "2026-06-30T14:00", "destination": "ZTH", "direction": "RET", "flight_date": "2026-10-03", "flight_number": "FR4", "price": 60.0},  # 7 noci
]


def test_report_has_destination_toggle():
    html = report.build_report_html(ROWS)
    assert "<html" in html.lower()
    assert "Kefalonia" in html and "Lefkada" in html and "Zakyntos" in html
    assert html.count("dest-btn") >= 3        # tlacidlo na kazdu destinaciu
    assert "133" in html                       # EFL 35+98 v tabulke (7 noci)
    assert "Najlacnejší round-trip" in html
    # per-destination labels: each panel must use its own IATA code
    assert "VIE→EFL" in html                  # EFL panel headers / legend
    assert "VIE→ZTH" in html                  # ZTH panel headers / legend


def test_report_empty():
    assert "Zatiaľ žiadne dáta" in report.build_report_html([])


def test_write_report_creates_file(tmp_path):
    out = tmp_path / "report.html"
    report.write_report(ROWS, out)
    assert out.exists() and "Kefalonia" in out.read_text(encoding="utf-8")
