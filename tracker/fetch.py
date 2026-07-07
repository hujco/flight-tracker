from datetime import date, timedelta

import requests

BASE_URL = "https://services-api.ryanair.com/farfnd/v4/oneWayFares"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
TIMEOUT = 20


def parse_fares(payload, direction, destination, origin=None):
    records = []
    for fare in payload.get("fares", []):
        ob = fare["outbound"]
        records.append(
            {
                "origin": origin,
                "destination": destination,
                "direction": direction,
                "flight_date": ob["departureDate"][:10],
                "flight_number": ob["flightNumber"],
                "price": ob["price"]["value"],
                "seats_left": None,
            }
        )
    return records


def days_in_month(year, month):
    days = []
    d = date(year, month, 1)
    while d.month == month:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def fetch_day(departure, arrival, day, session=None, currency="EUR"):
    client = session or requests
    params = {
        "departureAirportIataCode": departure,
        "arrivalAirportIataCode": arrival,
        "outboundDepartureDateFrom": day,
        "outboundDepartureDateTo": day,
        "currency": currency,
    }
    resp = client.get(BASE_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_leg(departure, arrival, direction, destination, origin, year, month,
              session=None, currency="EUR"):
    """Sken celého mesiaca pre jednu nohu. `origin` = odletisko kampane (VIE/BUD),
    `departure`/`arrival` = konkrétne letiská tejto nohy (pri RET sú prehodené)."""
    records = []
    for day in days_in_month(year, month):
        payload = fetch_day(departure, arrival, day, session=session, currency=currency)
        records.extend(parse_fares(payload, direction, destination, origin))
    return records


def fetch_fixed_leg(departure, arrival, direction, destination, origin, days,
                    session=None, currency="EUR"):
    """Ako fetch_leg, ale len pre zadané konkrétne dni (striktné fixné itineráre)."""
    records = []
    for day in days:
        payload = fetch_day(departure, arrival, day, session=session, currency=currency)
        records.extend(parse_fares(payload, direction, destination, origin))
    return records
