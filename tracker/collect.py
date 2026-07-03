from . import config, db, fetch


def collect_once(conn, observed_at, destinations=None, origin=None,
                 year=None, month=None, currency=None, session=None):
    destinations = destinations if destinations is not None else config.DESTINATIONS
    origin = origin if origin is not None else config.ORIGIN
    year = year if year is not None else config.YEAR
    month = month if month is not None else config.MONTH
    currency = currency if currency is not None else config.CURRENCY

    records = []
    for dst in destinations:
        code = dst["code"]
        records.extend(fetch.fetch_leg(
            origin, code, "OUT", code, year, month, session=session, currency=currency))
        records.extend(fetch.fetch_leg(
            code, origin, "RET", code, year, month, session=session, currency=currency))
    # vsetky volania presli -> az teraz jeden transakcny insert
    return db.insert_observations(conn, observed_at, records)
