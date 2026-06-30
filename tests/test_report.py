from tracker import report

ROWS = [
    {"observed_at": "2026-06-30T14:00", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 35.0},
    # navrat 3.10. = 7 noci -> v platnom rozsahu 5-10 noci (config)
    {"observed_at": "2026-06-30T14:00", "direction": "RET", "flight_date": "2026-10-03", "flight_number": "FR7311", "price": 98.0},
]


def test_build_report_html_contains_sections_and_total():
    html = report.build_report_html(ROWS)
    assert "<html" in html.lower()
    assert "Vývoj ceny" in html
    assert "Najlacnejší round-trip" in html
    assert "133" in html  # 35 + 98 v tabulke


def test_build_report_html_handles_empty():
    html = report.build_report_html([])
    assert "Zatiaľ žiadne dáta" in html


def test_write_report_creates_file(tmp_path):
    out = tmp_path / "report.html"
    report.write_report(ROWS, out)
    assert out.exists()
    assert "Vývoj ceny" in out.read_text(encoding="utf-8")
