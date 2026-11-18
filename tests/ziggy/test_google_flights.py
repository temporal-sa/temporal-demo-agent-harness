# Real flight search through SerpApi, and the fall back to simulated flights after
# REAL_FLIGHT_ATTEMPTS failed attempts. No network: SerpApi is replaced by a mock transport.
#
# Run with: uv run pytest tests/ziggy/test_google_flights.py -v

from __future__ import annotations

import dataclasses

import httpx
import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agent_harness_demo.ziggy import activities, google_flights

# Shaped like SerpApi's documented google_flights response, trimmed to the fields we read.
NONSTOP = {
    "flights": [
        {
            "departure_airport": {"id": "SFO", "time": "2026-12-18 08:05"},
            "arrival_airport": {"id": "JFK", "time": "2026-12-18 16:40"},
            "airline": "United",
            "flight_number": "UA 1234",
        }
    ],
    "price": 289,
}
CONNECTION = {
    "flights": [
        {
            "departure_airport": {"id": "SFO", "time": "2026-12-18 06:00"},
            "arrival_airport": {"id": "DEN", "time": "2026-12-18 09:30"},
            "airline": "Frontier",
            "flight_number": "F9 615",
        },
        {
            "departure_airport": {"id": "DEN", "time": "2026-12-18 10:45"},
            "arrival_airport": {"id": "JFK", "time": "2026-12-18 16:55"},
            "airline": "Frontier",
            "flight_number": "F9 2002",
        },
    ],
    "price": 154,
}
# A leg without a usable flight number is skipped, not fatal.
UNNUMBERED = {**NONSTOP, "flights": [{**NONSTOP["flights"][0], "flight_number": ""}]}


def serpapi(monkeypatch, handler) -> list[httpx.Request]:
    """Route google_flights' HTTP calls to `handler`, with an API key set."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        google_flights.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(record), **kwargs),
    )
    monkeypatch.setattr(google_flights, "SERPAPI_API_KEY", "test-key")
    return seen


def flights_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"best_flights": [NONSTOP], "other_flights": [UNNUMBERED, CONNECTION]}
    )


def on_attempt(attempt: int) -> ActivityEnvironment:
    env = ActivityEnvironment()
    env.info = dataclasses.replace(env.info, attempt=attempt)
    return env


async def test_real_flights_carry_their_flight_numbers_and_prices(monkeypatch):
    seen = serpapi(monkeypatch, flights_response)

    flights = await on_attempt(1).run(activities._real_flights, "SFO", "JFK", "2026-12-18")

    assert [f.flight_id for f in flights] == [
        "FL-SFOJFK-20261218-UA1234",
        "FL-SFOJFK-20261218-F9615-F92002",
    ]
    nonstop, connection = flights
    assert (nonstop.airline, nonstop.departure_time, nonstop.arrival_time) == ("United", "08:05", "16:40")
    assert (nonstop.price_usd, nonstop.stops) == (289.0, 0)
    assert [f.price_usd for f in nonstop.fares] == [289.0, 462.4, 982.6]
    assert (connection.stops, connection.arrival_time) == (1, "16:55")
    assert dict(seen[0].url.params) == {
        "engine": "google_flights", "type": "2", "departure_id": "SFO", "arrival_id": "JFK",
        "outbound_date": "2026-12-18", "currency": "USD", "hl": "en", "api_key": "test-key",
    }


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_a_failed_attempt_raises_so_temporal_retries_it(monkeypatch, status):
    serpapi(monkeypatch, lambda request: httpx.Response(status, json={"error": "nope"}))

    with pytest.raises(ApplicationError) as raised:
        await on_attempt(activities.REAL_FLIGHT_ATTEMPTS - 1).run(
            activities._real_flights, "SFO", "JFK", "2026-12-18"
        )

    assert not raised.value.non_retryable
    assert raised.value.type == "FlightApiUnavailable"
    assert f"HTTP {status}" in raised.value.message


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"error": "Your account has run out of searches."}),
        # SerpApi answers a route with no results with a 200 and an error.
        httpx.Response(200, json={"error": "Google Flights hasn't returned any results."}),
        httpx.Response(200, json={"best_flights": [UNNUMBERED]}),
        httpx.Response(502, text="<html>Bad gateway</html>"),
    ],
)
async def test_the_last_attempt_falls_back_to_simulated_flights(monkeypatch, response):
    serpapi(monkeypatch, lambda request: response)

    flights = await on_attempt(activities.REAL_FLIGHT_ATTEMPTS).run(
        activities._real_flights, "SFO", "JFK", "2026-12-18"
    )

    assert flights is None


async def test_a_network_failure_counts_as_a_failed_attempt(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    serpapi(monkeypatch, refuse)

    with pytest.raises(ApplicationError):
        await on_attempt(1).run(activities._real_flights, "SFO", "JFK", "2026-12-18")


async def test_without_a_key_search_never_calls_the_api(monkeypatch):
    seen = serpapi(monkeypatch, flights_response)
    monkeypatch.setattr(google_flights, "SERPAPI_API_KEY", "")

    assert await on_attempt(1).run(activities._real_flights, "SFO", "JFK", "2026-12-18") is None
    assert seen == []


async def test_booking_a_real_flight_uses_its_real_price(monkeypatch):
    seen = serpapi(monkeypatch, flights_response)

    flight = await on_attempt(1).run(
        activities._bookable_flight, "FL-SFOJFK-20261218-F9615-F92002"
    )

    assert flight.price_usd == 154.0
    # The identical search, so SerpApi can answer it from its free one-hour cache.
    assert seen[0].url.params["outbound_date"] == "2026-12-18"


async def test_booking_a_flight_google_no_longer_lists_asks_for_a_new_search(monkeypatch):
    serpapi(monkeypatch, flights_response)

    with pytest.raises(ApplicationError) as raised:
        await on_attempt(1).run(activities._bookable_flight, "FL-SFOJFK-20261218-DL400")

    assert raised.value.non_retryable


async def test_booking_a_real_flight_while_the_api_is_down_uses_a_simulated_price(monkeypatch):
    serpapi(monkeypatch, lambda request: httpx.Response(429, json={"error": "out of searches"}))
    flight_id = "FL-SFOJFK-20261218-UA1234"

    flight = await on_attempt(activities.REAL_FLIGHT_ATTEMPTS).run(
        activities._bookable_flight, flight_id
    )

    assert flight == activities._flight(flight_id)


async def test_booking_a_simulated_flight_never_calls_the_api(monkeypatch):
    seen = serpapi(monkeypatch, flights_response)

    flight = await on_attempt(1).run(activities._bookable_flight, "FL-SFOJFK-20261218-003")

    assert flight == activities._flight("FL-SFOJFK-20261218-003")
    assert seen == []


@pytest.mark.parametrize(
    "flight_id, valid",
    [
        ("FL-SFOJFK-20261218-003", True),
        ("FL-SFOJFK-20261218-UA1234", True),
        ("FL-SFOJFK-20261218-B6615-9W12", True),
        ("FL-SFOJFK-20261218-12345", False),  # two digits can't be an airline code
        ("FL-SFOJFK-20261218-UA", False),
        ("UA1234", False),
    ],
)
def test_flight_ids(flight_id, valid):
    if valid:
        activities._require_flight(flight_id)
    else:
        with pytest.raises(ApplicationError):
            activities._require_flight(flight_id)
