"""Domain models for the simulated travel-booking activities.

Request/response pairs that cross the Temporal activity boundary (pydantic, so the
project's pydantic data converter serializes them). Distinct from ``models.py``, which
holds the agent's accepted *message* type (:class:`RunScript`).

No ``from __future__ import annotations`` — these cross Temporal's pydantic converter,
and stringized annotations on nested models trip its TypeAdapter build. Concrete
annotations, nested models defined before the responses that reference them.
"""

from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------


FareLevel = Literal["economy", "premium", "business"]


class Fare(BaseModel):
    level: FareLevel
    price_usd: float
    changeable: bool


class Flight(BaseModel):
    flight_id: str
    airline: str
    departure_time: str
    arrival_time: str
    price_usd: float
    """The economy fare, the lowest on the flight."""
    stops: int
    fares: list[Fare]


class FlightSearchRequest(BaseModel):
    origin: str
    destination: str
    date: str


class FlightSearchResponse(BaseModel):
    flights: list[Flight]


class Seat(BaseModel):
    seat: str
    """Row and letter, such as "14C"."""
    cabin: FareLevel
    extra_usd: float
    """Added to the fare: economy exit rows cost extra."""
    features: list[str]
    """What the seat is like, good and bad: "window", "exit row", "no under-seat storage"."""


class SeatMapRequest(BaseModel):
    flight_id: str


class SeatMapResponse(BaseModel):
    flight_id: str
    open_seats: list[Seat]


class FlightBookingRequest(BaseModel):
    flight_id: str
    passenger_name: str
    fare: FareLevel = "economy"


class FlightBookingResponse(BaseModel):
    confirmation_code: str
    flight_id: str
    passenger_name: str
    fare: FareLevel
    price_usd: float
    status: str


class SeatSelectionRequest(BaseModel):
    """Choose a seat on a flight already booked; the booking details must match its code."""

    confirmation_code: str
    flight_id: str
    passenger_name: str
    fare: FareLevel
    seat: str


class SeatSelectionResponse(BaseModel):
    confirmation_code: str
    seat: str
    features: list[str]
    extra_usd: float
    status: str


# ---------------------------------------------------------------------------
# Hotels
# ---------------------------------------------------------------------------


class Hotel(BaseModel):
    hotel_id: str
    name: str
    star_rating: int
    price_per_night_usd: float
    neighborhood: str


class HotelSearchRequest(BaseModel):
    city: str
    check_in: str
    check_out: str


class HotelSearchResponse(BaseModel):
    hotels: list[Hotel]


class HotelBookingRequest(BaseModel):
    hotel_id: str
    guest_name: str


class HotelBookingResponse(BaseModel):
    confirmation_code: str
    hotel_id: str
    guest_name: str
    status: str
