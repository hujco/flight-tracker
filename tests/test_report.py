from tracker import config, report

# Staré VIE dáta v DB ostávajú (historia), ale report ich už nesmie zobrazovať:
# ubytovanie je fixne na 6.9. a VIE↔PVK v ten den nelieta.
VIE_ROWS = [
    {"observed_at": "2026-06-30T14:00", "origin": "VIE", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR1", "price": 40.0},
    {"observed_at": "2026-06-30T14:00", "origin": "VIE", "destination": "PVK", "direction": "RET", "flight_date": "2026-10-03", "flight_number": "FR2", "price": 70.0},  # 110
]

# BUD: nas termin (6->13, spolu 45) + druhy, LACNEJSI termin (1->8, spolu 30).
_BUD_PRIMARY = [
    {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-06", "flight_number": "W6A", "price": 20.0},
    {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "RET", "flight_date": "2026-09-13", "flight_number": "W6B", "price": 25.0},
]
_BUD_ALT = [
    {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-01", "flight_number": "W6C", "price": 10.0},
    {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "RET", "flight_date": "2026-09-08", "flight_number": "W6D", "price": 20.0},
]


def test_report_shows_only_our_flight():
    html = report.build_report_html(VIE_ROWS + _BUD_PRIMARY)
    assert "hero" in html and "Náš let" in html
    assert "06.09.2026" in html and "13.09.2026" in html
    assert "45 €" in html and f"Spolu {config.PERSONS} os." in html and "90" in html


def test_report_drops_vienna_entirely():
    # Viedeň nelieta náš termín -> nesmie sa objaviť ani ako porovnanie,
    # ani ako "iné termíny". Predtým dostávala odznak "najlacnejšie".
    html = report.build_report_html(VIE_ROWS + _BUD_PRIMARY)
    assert "Viedne" not in html and "(VIE)" not in html and "VIE→PVK" not in html
    assert "110" not in html                  # VIE round-trip cena
    assert "cmp-section" not in html and "cmp-grid" not in html
    assert "Odkiaľ sa oplatí letieť" not in html


def test_report_drops_other_dates_section():
    html = report.build_report_html(VIE_ROWS + _BUD_PRIMARY + _BUD_ALT)
    assert "Iné termíny" not in html and "class='secondary'" not in html
    assert "Najlacnejší round-trip" not in html
    assert "Dĺžka pobytu" not in html


def test_hero_price_is_our_date_not_the_cheapest_one():
    # Hero musi ukazat 45 € (6->13), NIE 30 € (1->8), aj ked 1->8 je lacnejsi.
    html = report.build_report_html(VIE_ROWS + _BUD_PRIMARY + _BUD_ALT)
    assert "45 €" in html and "30 €" not in html
    assert "01.09.2026" not in html and "08.09.2026" not in html


def test_report_only_vie_data_says_no_data_for_our_trip():
    html = report.build_report_html(VIE_ROWS)
    assert "Pre náš termín zatiaľ žiadne dáta" in html


def test_report_default_persons_matches_config():
    assert report._DEFAULT_PERSONS == config.PERSONS
    assert config.PERSONS in report._PERSONS_OPTIONS


# --- verdikt: cisla na rozhodnutie -------------------------------------------

def _at(ts, out_p, ret_p):
    return [dict(_BUD_PRIMARY[0], observed_at=ts, price=out_p),
            dict(_BUD_PRIMARY[1], observed_at=ts, price=ret_p)]


def test_verdict_shows_percentile_and_countdown():
    rows = _at("2026-08-01T06:00", 20.0, 25.0) + _at("2026-08-07T06:00", 40.0, 45.0)
    html = report.build_report_html(rows)
    assert "percentil" in html                 # kde sme voci historii
    assert "Za 7 dní" in html and "Do odletu" in html


def test_verdict_flags_expensive_when_at_top_of_history():
    # 3 zo 4 merani lacnejsie -> 75. percentil -> "drahe"
    rows = (_at("2026-08-01T06:00", 20.0, 25.0) + _at("2026-08-03T06:00", 22.0, 25.0)
            + _at("2026-08-05T06:00", 24.0, 25.0) + _at("2026-08-07T06:00", 60.0, 65.0))
    html = report.build_report_html(rows)
    assert "Drahé oproti histórii" in html and "verdict-bad" in html


def test_verdict_flags_cheap_when_at_bottom_of_history():
    rows = (_at("2026-08-01T06:00", 60.0, 65.0) + _at("2026-08-03T06:00", 58.0, 65.0)
            + _at("2026-08-05T06:00", 56.0, 65.0) + _at("2026-08-07T06:00", 20.0, 25.0))
    html = report.build_report_html(rows)
    assert "Lacné oproti histórii" in html and "verdict-good" in html


def test_verdict_absent_with_single_measurement():
    # jedno meranie -> percentil ani trend nedavaju zmysel
    html = report.build_report_html(_BUD_PRIMARY)
    assert "percentil" not in html


# --- spravanie hera pri minime (nezmenene) ------------------------------------

def test_hero_shows_lowest_so_far():
    older = [dict(r, observed_at="2026-06-29T14:00", price=r["price"] + 5) for r in _BUD_PRIMARY]
    html = report.build_report_html(older + _BUD_PRIMARY)
    assert "45 €" in html and "najnižšie" in html.lower()


def test_hero_shows_lowest_above_current():
    older = [dict(r, observed_at="2026-06-29T14:00") for r in _BUD_PRIMARY]
    now = [dict(r, price=r["price"] + 5) for r in _BUD_PRIMARY]
    html = report.build_report_html(older + now)
    assert "Najnižšie doteraz" in html and "45 €/os" in html and "+10 €" in html
    assert "class='hero-low hero-low-hit'" not in html   # markup, nie CSS pravidlo


def test_hero_flat_price_is_not_a_buy_signal():
    older = [dict(r, observed_at="2026-06-29T14:00") for r in _BUD_PRIMARY]
    html = report.build_report_html(older + _BUD_PRIMARY)
    assert "Cena sa zatiaľ nehla" in html and "2 meraní" in html
    assert "class='hero-low hero-low-hit'" not in html   # markup, nie CSS pravidlo


def test_hero_persons_toggle_has_multiperson_caveat():
    html = report.build_report_html(_BUD_PRIMARY)
    assert "Počet osôb" in html
    assert "Suma za viac osôb je orientačná" in html


def test_hero_at_min_warns_about_few_seats():
    older = [dict(r, observed_at="2026-06-29T14:00", price=r["price"] + 5) for r in _BUD_PRIMARY]
    html = report.build_report_html(older + _BUD_PRIMARY)
    assert "class='hero-low hero-low-hit'" in html and "len pár sedadiel" in html


def test_hero_above_min_no_seat_warning():
    older = [dict(r, observed_at="2026-06-29T14:00") for r in _BUD_PRIMARY]
    now = [dict(r, price=r["price"] + 5) for r in _BUD_PRIMARY]
    assert "len pár sedadiel" not in report.build_report_html(older + now)


def test_hero_flat_price_no_seat_warning():
    older = [dict(r, observed_at="2026-06-29T14:00") for r in _BUD_PRIMARY]
    assert "len pár sedadiel" not in report.build_report_html(older + _BUD_PRIMARY)


# --- rezim "odlet uz je kupeny" ----------------------------------------------

def _bought(monkeypatch, paid=43.0):
    monkeypatch.setattr(config, "OUT_LEG_BOUGHT", True)
    monkeypatch.setattr(config, "OUT_LEG_PAID_EUR", paid)


def test_hero_headlines_return_when_outbound_bought(monkeypatch):
    _bought(monkeypatch)
    rows = _at("2026-08-01T06:00", 50.0, 130.0) + _at("2026-08-10T06:00", 43.0, 166.0)
    html = report.build_report_html(rows)
    # velka cena = navrat (166), nie sucet (209) — o odlete uz nerozhodujeme
    assert "<div class='hero-price'>166 €" in html
    assert "<div class='hero-price'>209 €" not in html
    assert "Ostáva kúpiť návrat" in html
    assert "už kúpený" in html and "✓ kúpené 43 €" in html


def test_hero_shows_real_total_including_paid_leg(monkeypatch):
    _bought(monkeypatch, paid=43.0)
    rows = _at("2026-08-01T06:00", 50.0, 130.0) + _at("2026-08-10T06:00", 43.0, 166.0)
    html = report.build_report_html(rows)
    # 43 zaplatene + 166 navrat = 209 za osobu, 418 za dve
    assert "209 €" in html and "418 €" in html


def test_verdict_uses_return_series_when_outbound_bought(monkeypatch):
    _bought(monkeypatch)
    # navrat rastie (130 -> 150 -> 166) -> je na maxime, verdikt "drahe",
    # aj keby sucet vyzeral inak
    rows = (_at("2026-08-01T06:00", 60.0, 130.0) + _at("2026-08-04T06:00", 55.0, 150.0)
            + _at("2026-08-07T06:00", 50.0, 160.0) + _at("2026-08-10T06:00", 43.0, 166.0))
    html = report.build_report_html(rows)
    assert "Drahé oproti histórii" in html


def test_hero_headlines_total_when_nothing_bought():
    rows = _at("2026-08-01T06:00", 50.0, 130.0) + _at("2026-08-10T06:00", 43.0, 166.0)
    html = report.build_report_html(rows)
    assert "209 €" in html and "Ostáva kúpiť návrat" not in html


# --- cas: zbiera sa v UTC, cita sa v CEST ------------------------------------

def test_timestamp_is_shown_in_local_time_not_utc():
    # 06:43 UTC = 08:43 v Bratislave (CEST). Predtym stranka ukazala 06:43 a
    # vyzeralo to, ze data su o 2 h staršie nez su.
    assert report._fmt_dt("2026-08-08T06:43+00:00") == "08.08.2026 08:43"


def test_naive_timestamp_treated_as_utc():
    # stare riadky (pred prechodom na UTC) nemaju offset, ale boli pisane v UTC
    assert report._fmt_dt("2026-08-08T06:43") == report._fmt_dt("2026-08-08T06:43+00:00")


def test_age_badge_marks_stale_data():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(hours=1)).isoformat(timespec="minutes")
    old = (now - timedelta(hours=9)).isoformat(timespec="minutes")
    assert "age-stale" not in report._age_html(fresh)
    assert "age-stale" in report._age_html(old) and "pred 9 h" in report._age_html(old)


def test_report_empty():
    assert "Zatiaľ žiadne dáta" in report.build_report_html([])


def test_write_report_creates_file(tmp_path):
    out = tmp_path / "report.html"
    report.write_report(_BUD_PRIMARY, out)
    assert out.exists() and "Lefkada" in out.read_text(encoding="utf-8")
