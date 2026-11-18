"""Real one-way flight schedules and economy prices from Google Flights, through SerpApi.

Only search is real. Seat maps, booking, and seat selection stay simulated, so this client
returns just what a search result shows: the flights, their times, and the lowest fare.

SerpApi's free plan allows 250 searches a month. It caches identical requests for an hour
and doesn't count cached or failed searches, so the booking step's re-check of a price it
just showed is free.
"""

import os
import re
from dataclasses import dataclass

import httpx

SERPAPI_URL = "https://serpapi.com/search.json"

# Unset means flight search stays fully simulated, with no API calls and no retries.
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")

# Under the Activity's 30-second start-to-close timeout, so a slow API shows up as a failed
# attempt that Temporal retries rather than as a timeout.
_REQUEST_TIMEOUT_SECONDS = 20

# "UA 1234", "B6 615": a two-character IATA airline code, never two digits, and a number.
_FLIGHT_NUMBER = re.compile(r"^([A-Z][A-Z0-9]|\d[A-Z])\s*(\d{1,4})$")


class FlightApiError(Exception):
    """Google Flights didn't answer with flights: a rejected key, an exhausted quota, an
    outage, or a route with no results. The caller decides whether to retry or fall back."""


@dataclass(frozen=True)
class Itinerary:
    flight_numbers: list[str]
    """One per leg, without the space: ["UA1234", "UA567"]."""
    airline: str
    """The first leg's airline, as Google names it: "United"."""
    departure_time: str
    """Local "HH:MM" at the origin."""
    arrival_time: str
    """Local "HH:MM" at the destination."""
    price_usd: float
    """The economy fare for one adult."""


async def search(origin: str, destination: str, date: str) -> list[Itinerary]:
    """One-way economy itineraries for one adult, in Google's order (best first).

    Raises FlightApiError for any failure. Itineraries with a leg whose flight number
    isn't an airline code and number are skipped rather than failing the search.
    """
    params = {
        "engine": "google_flights",
        "type": "2",  # one way
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": date,
        "currency": "USD",
        "hl": "en",
        "api_key": SERPAPI_API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(SERPAPI_URL, params=params)
    except httpx.HTTPError as err:
        raise FlightApiError(f"request failed: {err!r}") from err

    try:
        body = response.json()
    except ValueError:
        body = {}
    # SerpApi reports failures as {"error": "..."}: a 401 for a bad key, and also with a 200
    # when Google has no results for the route.
    if response.status_code != 200 or "error" in body:
        message = body.get("error") or response.text[:200]
        raise FlightApiError(f"HTTP {response.status_code}: {message}")

    itineraries = []
    for entry in body.get("best_flights", []) + body.get("other_flights", []):
        itinerary = _itinerary(entry)
        if itinerary:
            itineraries.append(itinerary)
    if not itineraries:
        raise FlightApiError("Google Flights returned no bookable itineraries")
    return itineraries


def _itinerary(entry: dict) -> Itinerary | None:
    legs = entry.get("flights") or []
    price = entry.get("price")
    if not legs or price is None:
        return None
    numbers = []
    for leg in legs:
        match = _FLIGHT_NUMBER.match(leg.get("flight_number", ""))
        if not match:
            return None
        numbers.append(match.group(1) + match.group(2))
    # Times come as "2026-12-18 08:05", local to each airport.
    departs = legs[0].get("departure_airport", {}).get("time", "")
    arrives = legs[-1].get("arrival_airport", {}).get("time", "")
    if not departs or not arrives:
        return None
    return Itinerary(
        flight_numbers=numbers,
        airline=legs[0].get("airline") or numbers[0][:2],
        departure_time=departs[-5:],
        arrival_time=arrives[-5:],
        price_usd=float(price),
    )
