from tracker import stats

ROWS = [
    # meranie 14:00
    {"observed_at": "2026-06-30T14:00", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 35.0},
    {"observed_at": "2026-06-30T14:00", "direction": "RET", "flight_date": "2026-09-30", "flight_number": "FR7311", "price": 98.0},
    {"observed_at": "2026-06-30T14:00", "direction": "RET", "flight_date": "2026-09-20", "flight_number": "FR7311", "price": 50.0},
    # meranie 15:00 (OUT zlacnel)
    {"observed_at": "2026-06-30T15:00", "direction": "OUT", "flight_date": "2026-09-26", "flight_number": "FR7310", "price": 30.0},
    {"observed_at": "2026-06-30T15:00", "direction": "RET", "flight_date": "2026-09-30", "flight_number": "FR7311", "price": 98.0},
]


def test_latest_observed_at():
    assert stats.latest_observed_at(ROWS) == "2026-06-30T15:00"
    assert stats.latest_observed_at([]) is None


def test_price_series_groups_by_flight_date_sorted():
    series = stats.price_series(ROWS, "OUT")
    assert series == {"2026-09-26": [("2026-06-30T14:00", 35.0), ("2026-06-30T15:00", 30.0)]}


def test_cheapest_roundtrip_now_excludes_return_before_outbound():
    combos = stats.cheapest_roundtrip_now(ROWS)
    # najnovsie meranie 15:00 ma OUT 26.9. a RET 30.9. -> jedina platna kombinacia
    assert combos == [
        {"out_date": "2026-09-26", "out_price": 30.0,
         "ret_date": "2026-09-30", "ret_price": 98.0, "total": 128.0}
    ]


def test_cheapest_roundtrip_over_time():
    series = stats.cheapest_roundtrip_over_time(ROWS)
    # 14:00: OUT 35 + RET 98 (RET 20.9 je pred odletom -> neplatny) = 133
    # 15:00: OUT 30 + RET 98 = 128
    assert series == [("2026-06-30T14:00", 133.0), ("2026-06-30T15:00", 128.0)]
