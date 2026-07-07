from . import config, db, fetch


def _month_records(origin, destinations, year, month, currency, session):
    """VIE-štýl: sken celého mesiaca pre každú destináciu (OUT aj RET)."""
    records = []
    for dst in destinations:
        code = dst["code"]
        records.extend(fetch.fetch_leg(
            origin, code, "OUT", code, origin, year, month,
            session=session, currency=currency))
        records.extend(fetch.fetch_leg(
            code, origin, "RET", code, origin, year, month,
            session=session, currency=currency))
    return records


def _fixed_records(origin, destinations, trips, currency, session):
    """BUD-štýl: len konkrétne odletové/návratové dni z fixných itinerárov."""
    out_days = sorted({t["out"] for t in trips})
    ret_days = sorted({t["ret"] for t in trips})
    records = []
    for dst in destinations:
        code = dst["code"]
        records.extend(fetch.fetch_fixed_leg(
            origin, code, "OUT", code, origin, out_days,
            session=session, currency=currency))
        records.extend(fetch.fetch_fixed_leg(
            code, origin, "RET", code, origin, ret_days,
            session=session, currency=currency))
    return records


def collect_once(conn, observed_at, destinations=None, origin=None,
                 year=None, month=None, currency=None, session=None,
                 bud_origin=None, bud_destinations=None, bud_trips=None):
    destinations = destinations if destinations is not None else config.DESTINATIONS
    origin = origin if origin is not None else config.ORIGIN
    year = year if year is not None else config.YEAR
    month = month if month is not None else config.MONTH
    currency = currency if currency is not None else config.CURRENCY
    bud_origin = bud_origin if bud_origin is not None else config.BUD_ORIGIN
    bud_destinations = bud_destinations if bud_destinations is not None else config.BUD_DESTINATIONS
    bud_trips = bud_trips if bud_trips is not None else config.BUD_TRIPS

    records = _month_records(origin, destinations, year, month, currency, session)
    if bud_trips:  # druhé odletisko: striktné fixné itineráre
        records += _fixed_records(bud_origin, bud_destinations, bud_trips, currency, session)

    # vsetky volania presli -> az teraz jeden transakcny insert
    return db.insert_observations(conn, observed_at, records)
