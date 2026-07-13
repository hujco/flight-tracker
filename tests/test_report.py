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


def test_report_compares_origins():
    # Lefkada ma VIE (110) aj BUD (45) -> porovnavacia hlavicka s verdiktom + spolocny graf
    rows = ROWS + [
        {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-06", "flight_number": "W6A", "price": 20.0},
        {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "RET", "flight_date": "2026-09-13", "flight_number": "W6B", "price": 25.0},  # 7 noci -> 45
    ]
    html = report.build_report_html(rows)
    # porovnavacie karty
    assert "cmp-grid" in html and "cmp-card" in html
    assert "(VIE)" in html and "(BUD)" in html
    # verdikt: BUD (45) lacnejsi o 65 oproti VIE (110)
    assert "Budapešť" in html and "lacnejšia" in html and "65" in html
    assert "najlacnejšie" in html             # odznak vitaza
    # pocitadlo osob: default 4 -> VIE 110*4=440, BUD 45*4=180
    assert "Počet osôb" in html and "pp-btn" in html
    assert "Spolu 4 os." in html
    assert "440" in html and "180" in html
    # detaily nizsie: obe odletiska, vlastne labely + ceny
    assert "BUD→PVK" in html and "VIE→PVK" in html
    assert "45" in html and "110" in html


def test_report_primary_trip_hero():
    # Nas hlavny let (BUD 6->13.9) sa zvyrazni navrchu s cenou a pocitadlom
    rows = ROWS + [
        {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-06", "flight_number": "W6A", "price": 20.0},
        {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "RET", "flight_date": "2026-09-13", "flight_number": "W6B", "price": 25.0},
    ]
    html = report.build_report_html(rows)
    assert "hero" in html and "Náš let" in html
    assert "06.09.2026" in html and "13.09.2026" in html   # fixny termin 6->13
    assert "Počet osôb" in html                            # pocitadlo v hero
    # cena/os = 45, default 4 osoby -> 180; jednotlive nohy 20 a 25
    assert "45 €" in html and "Spolu 4 os." in html and "180" in html
    # hero je pred porovnavacou sekciou v tele stranky
    assert html.index("class='hero'") < html.index("class='cmp-section'")


# BUD: nas termin (6->13, spolu 45) + druhy, LACNEJSI termin (1->8, spolu 30).
# Lacnejsi termin nesmie vyzerat ako cena nasho letu.
_BUD_PRIMARY = [
    {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-06", "flight_number": "W6A", "price": 20.0},
    {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "RET", "flight_date": "2026-09-13", "flight_number": "W6B", "price": 25.0},
]
_BUD_ALT = [
    {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "OUT", "flight_date": "2026-09-01", "flight_number": "W6C", "price": 10.0},
    {"observed_at": "2026-06-30T14:00", "origin": "BUD", "destination": "PVK", "direction": "RET", "flight_date": "2026-09-08", "flight_number": "W6D", "price": 20.0},
]


def test_hero_price_is_our_date_not_the_cheapest_one():
    # Hero musi ukazat 45 € (6->13), NIE 30 € (1->8), aj ked 1->8 je lacnejsi.
    html = report.build_report_html(ROWS + _BUD_PRIMARY + _BUD_ALT)
    hero = html[html.index("class='hero'"):html.index("class='secondary'")]
    assert "45 €" in hero and "30 €" not in hero
    assert "06.09.2026" in hero and "13.09.2026" in hero
    assert "01.09.2026" not in hero and "08.09.2026" not in hero


def test_other_dates_are_separated_below_hero():
    html = report.build_report_html(ROWS + _BUD_PRIMARY + _BUD_ALT)
    # poradie v tele: hero -> oddelovac 'iné termíny' -> porovnanie odletisk
    assert (html.index("class='hero'")
            < html.index("class='secondary'")
            < html.index("class='cmp-section'"))
    assert "Iné termíny" in html
    # karty/riadky s inym datumom su oznacene, nas termin tiez
    assert "iný termín" in html and "náš termín" in html


def test_hero_shows_lowest_so_far():
    older = [dict(r, observed_at="2026-06-29T14:00", price=r["price"] + 5) for r in _BUD_PRIMARY]
    html = report.build_report_html(ROWS + older + _BUD_PRIMARY)
    hero = html[html.index("class='hero'"):html.index("class='secondary'")]
    # teraz 45, predtym 55 -> teraz je nove minimum
    assert "45 €" in hero and "najnižšie" in hero.lower()


def test_hero_shows_lowest_above_current():
    # najnizsie bolo 45, teraz 55 -> ziadny zeleny signal, ukaz rozdiel
    older = [dict(r, observed_at="2026-06-29T14:00") for r in _BUD_PRIMARY]
    now = [dict(r, price=r["price"] + 5) for r in _BUD_PRIMARY]
    html = report.build_report_html(ROWS + older + now)
    hero = html[html.index("class='hero'"):html.index("class='secondary'")]
    assert "Najnižšie doteraz" in hero and "45 €/os" in hero and "+10 €" in hero
    assert "hero-low-hit" not in hero


def test_hero_flat_price_is_not_a_buy_signal():
    # cena sa nikdy nepohla -> neklamme zelenym "teraz je najnizsie"
    older = [dict(r, observed_at="2026-06-29T14:00") for r in _BUD_PRIMARY]
    html = report.build_report_html(ROWS + older + _BUD_PRIMARY)
    hero = html[html.index("class='hero'"):html.index("class='secondary'")]
    assert "Cena sa zatiaľ nehla" in hero and "2 meraní" in hero
    assert "hero-low-hit" not in hero


def test_hero_at_min_warns_about_few_seats():
    # teraz je na historickom minime (najlacnejsi fare bucket) -> varuj o sedadlach
    older = [dict(r, observed_at="2026-06-29T14:00", price=r["price"] + 5) for r in _BUD_PRIMARY]
    html = report.build_report_html(ROWS + older + _BUD_PRIMARY)
    hero = html[html.index("class='hero'"):html.index("class='secondary'")]
    assert "hero-low-hit" in hero
    assert "len pár sedadiel" in hero


def test_hero_above_min_no_seat_warning():
    # cena je nad minimom -> ziadny "kupuj hned" bucket signal -> ziadne varovanie o sedadlach
    older = [dict(r, observed_at="2026-06-29T14:00") for r in _BUD_PRIMARY]
    now = [dict(r, price=r["price"] + 5) for r in _BUD_PRIMARY]
    html = report.build_report_html(ROWS + older + now)
    hero = html[html.index("class='hero'"):html.index("class='secondary'")]
    assert "len pár sedadiel" not in hero


def test_hero_flat_price_no_seat_warning():
    # cena sa nikdy nepohla -> nevieme povedat ze je to najlacnejsi bucket -> ziadne varovanie
    older = [dict(r, observed_at="2026-06-29T14:00") for r in _BUD_PRIMARY]
    html = report.build_report_html(ROWS + older + _BUD_PRIMARY)
    hero = html[html.index("class='hero'"):html.index("class='secondary'")]
    assert "len pár sedadiel" not in hero


def test_report_empty():
    assert "Zatiaľ žiadne dáta" in report.build_report_html([])


def test_write_report_creates_file(tmp_path):
    out = tmp_path / "report.html"
    report.write_report(ROWS, out)
    assert out.exists() and "Lefkada" in out.read_text(encoding="utf-8")
