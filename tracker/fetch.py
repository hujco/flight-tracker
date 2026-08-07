from datetime import date, datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://services-api.ryanair.com/farfnd/v4/oneWayFares"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
TIMEOUT = 20


def make_session():
    """Session s retry/backoff. Jeden beh = ~62 sekvenčných requestov a zápis je
    atomický, takže bez retry zhodí jediný 503 celý zber (vrátane 61 úspešných)."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,          # 1s, 2s, 4s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _epoch_ms_to_iso(value):
    """`priceUpdated` chodí ako epoch v ms. None/nezmysel → None, nech nezhodí beh."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat(
            timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def parse_fares(payload, direction, destination, origin=None):
    records = []
    for fare in payload.get("fares", []):
        ob = fare.get("outbound")
        if not ob:
            continue
        price = (ob.get("price") or {}).get("value")
        if price is None:      # bez ceny je záznam bezcenný, ale nesmie zhodiť beh
            continue
        prev = ob.get("previousPrice")
        if isinstance(prev, dict):
            prev = prev.get("value")
        records.append(
            {
                "origin": origin,
                "destination": destination,
                "direction": direction,
                "flight_date": ob["departureDate"][:10],
                # celý timestamp: pri 05:50 odlete z BUD je čas materiálna informácia
                "departure_time": ob.get("departureDate"),
                "arrival_time": ob.get("arrivalDate"),
                "flight_number": ob["flightNumber"],
                "price": price,
                "currency": (ob.get("price") or {}).get("currencyCode"),
                # kedy Ryanair naposledy zmenil cenu — dá presný čas zmeny nezávisle
                # od toho, ako často meriame (cena sa mení len v ~21 % meraní)
                "price_updated": _epoch_ms_to_iso(ob.get("priceUpdated")),
                "previous_price": prev,
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
