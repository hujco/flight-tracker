from . import config, db, fetch


def collect_once(conn, observed_at, legs=None, year=None, month=None,
                 currency=None, session=None):
    legs = legs if legs is not None else config.LEGS
    year = year if year is not None else config.YEAR
    month = month if month is not None else config.MONTH
    currency = currency if currency is not None else config.CURRENCY

    records = []
    for leg in legs:
        records.extend(
            fetch.fetch_leg(
                leg["origin"], leg["destination"], leg["direction"],
                year, month, session=session, currency=currency,
            )
        )
    # vsetky volania presli -> az teraz jeden transakcny insert
    return db.insert_observations(conn, observed_at, records)
