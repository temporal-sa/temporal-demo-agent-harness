"""Simulated travel-booking activity implementations.

These activities return realistic-looking fake data so the sandbox workflow can be
exercised end-to-end without any real external APIs. The workflow exposes each one to
the sandboxed script as a *host function* (see ``workflow.py``); when the script calls
that host function, the workflow runs the matching activity here durably. The script
never touches Temporal — it just calls a plain function.

Each is an ``@agent.activity_tool_defn``, so when the workflow dispatches it (via
``run_tool``) the activity publishes its own ``tool_start``/``tool_end`` lifecycle events
on the turn stream — each host call the script makes shows up as a distinct tool
invocation, like any other harness tool. The decorated object is the in-workflow
dispatcher; the worker registers each one's durable activity body by handing ``ALL_TOOLS``
to ``AgentHarnessPlugin(tools=...)``.

No ``from __future__ import annotations`` here, for consistency with the rest of the
agent's Temporal-facing modules (stringized annotations trip the pydantic converter).
"""

import asyncio
import hashlib
import random
import re
from datetime import timedelta

from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.workflow import ActivityConfig

from temporal_agent_harness.harness import agent

from .travel_models import (
    Fare,
    FareLevel,
    Flight,
    FlightBookingRequest,
    FlightBookingResponse,
    FlightSearchRequest,
    FlightSearchResponse,
    Hotel,
    HotelBookingRequest,
    HotelBookingResponse,
    HotelSearchRequest,
    HotelSearchResponse,
    Seat,
    SeatMapRequest,
    SeatMapResponse,
)

# ---------------------------------------------------------------------------
# Simulated data
# ---------------------------------------------------------------------------

AIRLINES = ["United", "Delta", "American", "JetBlue", "Southwest", "Alaska"]
HOTEL_CHAINS = ["Marriott", "Hilton", "Hyatt", "IHG", "Best Western", "Radisson"]
NEIGHBORHOODS = {
    "New York": ["Midtown", "SoHo", "Upper East Side", "Chelsea", "Tribeca"],
    "San Francisco": ["Union Square", "Fisherman's Wharf", "SOMA", "Mission", "Nob Hill"],
    "Los Angeles": ["Hollywood", "Santa Monica", "Downtown", "Beverly Hills", "Venice"],
    "Chicago": ["The Loop", "River North", "Magnificent Mile", "Wicker Park", "Lincoln Park"],
    "Miami": ["South Beach", "Brickell", "Wynwood", "Coral Gables", "Coconut Grove"],
}
DEFAULT_NEIGHBORHOODS = ["Downtown", "City Center", "Old Town", "Waterfront", "Arts District"]

# Per-activity execution ceiling. Trivial for these simulated calls, but a real host
# function might do meaningful I/O; tune per tool if that ever matters. Lives on each
# tool's decorator now (the in-workflow approval/dispatch logic, if any, runs outside it).
_MONTY_ACTIVITY_TIMEOUT = timedelta(seconds=30)

# Cabins by row, with the seat letters in each row. Economy exit rows cost extra.
CABINS: dict[FareLevel, tuple[range, str]] = {
    "business": (range(1, 5), "ACDF"),
    "premium": (range(5, 10), "ABCDEF"),
    "economy": (range(10, 31), "ABCDEF"),
}
EXIT_ROWS = {12, 13}
EXIT_ROW_EXTRA_USD = 40.0

FLIGHT_ID = re.compile(r"^FL-[A-Z]{6}-\d{8}-\d{3}$")


def _make_ref(prefix: str, *parts: str) -> str:
    """Deterministic but realistic-looking confirmation code."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:6].upper()
    return f"{prefix}-{digest}"


def _flight_id(origin: str, destination: str, date: str, number: int) -> str:
    """`FL-SFOJFK-20261103-001`: the route, the date, and the flight's place in the results."""
    return f"FL-{origin}{destination}-{date.replace('-', '')}-{number:03d}"


def _flight(flight_id: str) -> Flight:
    """Everything about a flight follows from its ID, so search, the seat map, and booking
    agree on it without storing anything."""
    rng = random.Random(flight_id)
    dep_hour = rng.randint(6, 21)
    arr_hour = (dep_hour + rng.randint(2, 7)) % 24
    economy = round(rng.uniform(150, 800), 2)
    return Flight(
        flight_id=flight_id,
        airline=rng.choice(AIRLINES),
        departure_time=f"{dep_hour:02d}:{rng.choice(['00', '15', '30', '45'])}",
        arrival_time=f"{arr_hour:02d}:{rng.choice(['00', '15', '30', '45'])}",
        price_usd=economy,
        stops=rng.choices([0, 1, 2], weights=[5, 3, 1])[0],
        fares=[
            Fare(level="economy", price_usd=economy, changeable=False),
            Fare(level="premium", price_usd=round(economy * 1.6, 2), changeable=True),
            Fare(level="business", price_usd=round(economy * 3.4, 2), changeable=True),
        ],
    )


def _open_seats(flight_id: str) -> list[Seat]:
    """About a third of each cabin is still open, the same third every time."""
    rng = random.Random(f"seats:{flight_id}")
    return [
        Seat(
            seat=f"{row}{letter}",
            cabin=cabin,
            extra_usd=EXIT_ROW_EXTRA_USD if row in EXIT_ROWS else 0.0,
        )
        for cabin, (rows, letters) in CABINS.items()
        for row in rows
        for letter in letters
        if rng.random() < 0.3
    ]


def _seat_charge(flight_id: str, seat_code: str | None, fare: FareLevel) -> float:
    """The extra charge for a requested seat, refusing one that's taken or in another cabin."""
    if seat_code is None:
        return 0.0
    seat = next((s for s in _open_seats(flight_id) if s.seat == seat_code), None)
    if seat is None:
        raise ApplicationError(
            f"Seat {seat_code} isn't open on {flight_id}; pick one from get_seat_map.",
            non_retryable=True,
        )
    if seat.cabin != fare:
        raise ApplicationError(
            f"Seat {seat_code} is in {seat.cabin}, not {fare}; change the fare or the seat.",
            non_retryable=True,
        )
    return seat.extra_usd


def _require_flight(flight_id: str) -> None:
    if not FLIGHT_ID.match(flight_id):
        raise ApplicationError(
            f"No flight {flight_id}; use a flight_id from search_flights.", non_retryable=True
        )


# ---------------------------------------------------------------------------
# Activity implementations
# ---------------------------------------------------------------------------


@agent.activity_tool_defn(
    name="search_flights",
    activity_config=ActivityConfig(start_to_close_timeout=_MONTY_ACTIVITY_TIMEOUT),
)
async def search_flights_activity(request: FlightSearchRequest) -> FlightSearchResponse:
    """Search for available flights between two airports on a given date."""
    activity.logger.info(
        "Searching flights %s -> %s on %s", request.origin, request.destination, request.date
    )

    # Simulate the latency of querying an external flight-search API.
    await asyncio.sleep(random.uniform(3.0, 5.0))

    rng = random.Random(f"{request.origin}{request.destination}{request.date}")
    count = rng.randint(2, 5)
    return FlightSearchResponse(
        flights=[
            _flight(_flight_id(request.origin, request.destination, request.date, number))
            for number in range(1, count + 1)
        ]
    )


@agent.activity_tool_defn(
    name="get_seat_map",
    activity_config=ActivityConfig(start_to_close_timeout=_MONTY_ACTIVITY_TIMEOUT),
)
async def get_seat_map_activity(request: SeatMapRequest) -> SeatMapResponse:
    """List the open seats on a flight, by cabin, with any extra charge for each."""
    activity.logger.info("Fetching the seat map for %s", request.flight_id)
    _require_flight(request.flight_id)

    # Simulate the latency of asking the airline for its seat map.
    await asyncio.sleep(random.uniform(1.5, 3.0))

    return SeatMapResponse(flight_id=request.flight_id, open_seats=_open_seats(request.flight_id))


@agent.activity_tool_defn(
    name="search_hotels",
    activity_config=ActivityConfig(start_to_close_timeout=_MONTY_ACTIVITY_TIMEOUT),
)
async def search_hotels_activity(request: HotelSearchRequest) -> HotelSearchResponse:
    """Search for available hotels in a city for the given date range."""
    activity.logger.info(
        "Searching hotels in %s (%s to %s)", request.city, request.check_in, request.check_out
    )

    # Simulate the latency of querying an external hotel-search API.
    await asyncio.sleep(random.uniform(3.0, 5.0))

    rng = random.Random(f"{request.city}{request.check_in}{request.check_out}")
    neighborhoods = NEIGHBORHOODS.get(request.city, DEFAULT_NEIGHBORHOODS)
    num_results = rng.randint(2, 5)
    hotels = []
    for i in range(num_results):
        chain = rng.choice(HOTEL_CHAINS)
        neighborhood = rng.choice(neighborhoods)
        stars = rng.randint(2, 5)
        price = round(rng.uniform(80, 450), 2)

        hotels.append(
            Hotel(
                hotel_id=f"HT-{request.city[:3].upper()}-{i + 1:03d}",
                name=f"{chain} {neighborhood}",
                star_rating=stars,
                price_per_night_usd=price,
                neighborhood=neighborhood,
            )
        )

    return HotelSearchResponse(hotels=hotels)


@agent.activity_tool_defn(
    name="book_flight",
    activity_config=ActivityConfig(start_to_close_timeout=_MONTY_ACTIVITY_TIMEOUT),
)
async def book_flight_activity(request: FlightBookingRequest) -> FlightBookingResponse:
    """Book a flight at a fare level, optionally in a chosen seat, and return a confirmation
    code. The seat must be open and in the fare's cabin."""
    activity.logger.info(
        "Booking %s (%s, seat %s) for %s",
        request.flight_id, request.fare, request.seat or "any", request.passenger_name,
    )
    _require_flight(request.flight_id)
    fare = next(f for f in _flight(request.flight_id).fares if f.level == request.fare)
    seat_extra = _seat_charge(request.flight_id, request.seat, request.fare)

    # Simulate the latency of confirming the booking with the airline.
    await asyncio.sleep(random.uniform(4.0, 6.0))

    return FlightBookingResponse(
        confirmation_code=_make_ref("AIR", request.flight_id, request.passenger_name, request.fare),
        flight_id=request.flight_id,
        passenger_name=request.passenger_name,
        fare=request.fare,
        seat=request.seat,
        price_usd=round(fare.price_usd + seat_extra, 2),
        status="confirmed",
    )


@agent.activity_tool_defn(
    name="book_hotel",
    activity_config=ActivityConfig(start_to_close_timeout=_MONTY_ACTIVITY_TIMEOUT),
)
async def book_hotel_activity(request: HotelBookingRequest) -> HotelBookingResponse:
    """Book a specific hotel for a guest and return a confirmation code."""
    activity.logger.info("Booking hotel %s for %s", request.hotel_id, request.guest_name)

    # Simulate the latency of confirming the booking with the hotel.
    await asyncio.sleep(random.uniform(4.0, 6.0))

    return HotelBookingResponse(
        confirmation_code=_make_ref("HTL", request.hotel_id, request.guest_name),
        hotel_id=request.hotel_id,
        guest_name=request.guest_name,
        status="confirmed",
    )


# The agent's toolset, declared once. The module-level names above are the in-workflow
# dispatchers; each workflow wraps this list in a Code Mode tool (exposing them to the script
# as host functions), and the worker hands the same list to ``AgentHarnessPlugin(tools=...)``,
# which registers each one's durable activity body.
ALL_TOOLS = [
    search_flights_activity,
    get_seat_map_activity,
    search_hotels_activity,
    book_flight_activity,
    book_hotel_activity,
]
