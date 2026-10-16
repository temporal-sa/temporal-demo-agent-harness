"""Asking the traveler to choose between trip options or hotels, answered in their browser.

`ask_traveler_to_choose` and `ask_traveler_to_choose_hotel` are harness *callback tools*: they
have no body. When a script calls it,
the agent publishes the options and waits, durably and for as long as it takes, until a client
answers. The demo view draws each option as a card and answers with the traveler's pick, so
the script carries on with a typed `Choice` instead of the model guessing from free text.

No ``from __future__ import annotations`` here: these models cross Temporal's pydantic
converter, like the rest of the agent's Temporal-facing modules.
"""

from pydantic import BaseModel

from temporal_agent_harness.harness import agent

from .travel_models import FareLevel


class OptionLeg(BaseModel):
    flight_id: str
    origin: str
    destination: str
    date: str
    """YYYY-MM-DD."""
    airline: str
    departure_time: str
    arrival_time: str
    stops: int


class OptionFare(BaseModel):
    level: FareLevel
    total_usd: float
    """Every leg of the option at this fare."""


class TripOption(BaseModel):
    option_id: str
    title: str
    """A few words a traveler would recognize: "Full Christmas week"."""
    legs: list[OptionLeg]
    fares: list[OptionFare]
    note: str | None = None
    """Anything worth weighing: "Returns on New Year's Day"."""


class ChoiceRequest(BaseModel):
    question: str
    options: list[TripOption]


class Choice(BaseModel):
    option_id: str | None
    """The option picked, or None if the traveler wants something else."""
    fare: FareLevel | None
    comment: str | None = None
    """What the traveler said instead of, or as well as, picking."""


@agent.callback_tool_defn(inherently_safe=True)
async def ask_traveler_to_choose(request: ChoiceRequest) -> Choice:
    """Show the traveler two or more trip options as cards, with each fare's total, and wait
    for them to pick an option and fare, or to say what they want instead."""
    ...


class HotelOption(BaseModel):
    hotel_id: str
    name: str
    neighborhood: str
    star_rating: int
    price_per_night_usd: float
    total_usd: float
    """The whole stay: the nightly price times the nights."""
    note: str | None = None
    """Anything worth weighing: "Walk to the conference venue"."""


class HotelChoiceRequest(BaseModel):
    question: str
    city: str
    check_in: str
    """YYYY-MM-DD."""
    check_out: str
    """YYYY-MM-DD."""
    options: list[HotelOption]


class HotelChoice(BaseModel):
    hotel_id: str | None
    """The hotel picked, or None if the traveler wants something else."""
    comment: str | None = None
    """What the traveler said instead of, or as well as, picking."""


@agent.callback_tool_defn(inherently_safe=True)
async def ask_traveler_to_choose_hotel(request: HotelChoiceRequest) -> HotelChoice:
    """Show the traveler two or more hotels for one city and stay as cards, with each stay's
    total, and wait for them to pick one or to say what they want instead."""
    ...


CHOICE_TOOLS = [ask_traveler_to_choose, ask_traveler_to_choose_hotel]
CHOICE_TOOL_NAMES = [tool.__name__ for tool in CHOICE_TOOLS]
