"""Play a whole trip through the demo view without a model or an API key.

Starts a script-only Monty session (MontyDynamicAgent) as the local dev user and sends it one
script that plans a multi-city trip: searches run in parallel, two itineraries appear as cards
for the traveler to pick (a callback tool, answered in the browser), then each booking lands
on the trip board. Every search and booking waits for approval in the demo view, as it would with
the conversational agent. The real Workflow, Activities, approvals, and trip board all run;
only the model is missing, so there is no chat reply and the message box doesn't apply.

    uv run python -m scripts.preview_trip            # web and worker already running
    uv run python -m scripts.preview_trip --no-approvals
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets

from temporal_agent_harness.harness.agent_client import AgentClient
from temporal_agent_harness.harness.agent_protocol import AgentConfig, ToolApprovalPolicy
from temporal_agent_harness.plugin import AgentHarnessPlugin

from agent_harness_demo import config
from agent_harness_demo.monty.choices import CHOICE_TOOL_NAMES
from agent_harness_demo.monty.trip_board import BOARD_TOOL_NAMES
from agent_harness_demo.web import DEV_USER, prefix_for

SCRIPT = """
import asyncio

async def main():
    trip = await open_trip({"description": "SFO to New York to London and home, Nov 3-12",
                            "traveler": "Ada Lovelace",
                            "tasks": ["Book SFO to JFK", "Book JFK to LHR", "Book LHR to SFO",
                                      "Book a hotel in New York", "Book a hotel in London"]})
    trip_id = trip["trip_id"]

    legs = [("SFO", "JFK", "2026-11-03"), ("JFK", "LHR", "2026-11-06"), ("LHR", "SFO", "2026-11-12")]
    stays = [("New York", "2026-11-03", "2026-11-06", 3), ("London", "2026-11-06", "2026-11-12", 6)]

    # Every search at once: each is its own durable Activity. Calls of one type share an
    # inner gather, because the sandbox type-checks each result.
    flights_found, hotels_found = await asyncio.gather(
        asyncio.gather(*[search_flights({"origin": o, "destination": d, "date": day}) for o, d, day in legs]),
        asyncio.gather(*[search_hotels({"city": c, "check_in": i, "check_out": out}) for c, i, out, _ in stays]),
    )

    # Two ways to fly it, offered as cards; the traveler's pick comes back as a typed Choice.
    itineraries = {
        "cheapest": [min(found["flights"], key=lambda f: f["price_usd"]) for found in flights_found],
        "earliest": [min(found["flights"], key=lambda f: f["departure_time"]) for found in flights_found],
    }
    titles = {"cheapest": "Lowest fares", "earliest": "Earliest departures"}
    options: list[TripOption] = []
    for key, chosen_flights in itineraries.items():
        option: TripOption = {
            "option_id": key,
            "title": titles[key],
            "legs": [
                {"flight_id": f["flight_id"], "origin": o, "destination": d, "date": day,
                 "airline": f["airline"], "departure_time": f["departure_time"],
                 "arrival_time": f["arrival_time"], "stops": f["stops"]}
                for f, (o, d, day) in zip(chosen_flights, legs)
            ],
            "fares": [
                {"level": level, "total_usd": round(sum(x["price_usd"] for f in chosen_flights
                                                     for x in f["fares"] if x["level"] == level), 2)}
                for level in ["economy", "premium", "business"]
            ],
        }
        options.append(option)
    choice = await ask_traveler_to_choose({"question": "Which way would you like to fly?", "options": options})
    flights = itineraries[choice["option_id"] or "cheapest"]
    fare = choice["fare"] or "economy"

    # Then a hotel in each city, one question per city, the same way.
    hotels = []
    for (city, check_in, check_out, nights), found in zip(stays, hotels_found):
        offered: list[HotelOption] = []
        for h in found["hotels"][:3]:
            offer: HotelOption = {"hotel_id": h["hotel_id"], "name": h["name"],
                                  "neighborhood": h["neighborhood"], "star_rating": h["star_rating"],
                                  "price_per_night_usd": h["price_per_night_usd"],
                                  "total_usd": round(h["price_per_night_usd"] * nights, 2)}
            offered.append(offer)
        picked = await ask_traveler_to_choose_hotel({"question": "Where would you like to stay in " + city + "?",
                                                     "city": city, "check_in": check_in,
                                                     "check_out": check_out, "options": offered})
        stay = found["hotels"][0]
        for h in found["hotels"]:
            if h["hotel_id"] == picked["hotel_id"]:
                stay = h
        hotels.append(stay)

    # Then every booking at once, flights and hotels each in their own gather.
    flights_booked, hotels_booked = await asyncio.gather(
        asyncio.gather(*[
            book_flight({"flight_id": f["flight_id"], "passenger_name": "Ada Lovelace", "fare": fare})
            for f in flights
        ]),
        asyncio.gather(*[book_hotel({"hotel_id": h["hotel_id"], "guest_name": "Ada Lovelace"}) for h in hotels]),
    )
    for (o, d, _), flight, booked in zip(legs, flights, flights_booked):
        await record_booking({"trip_id": trip_id, "kind": "flight",
                              "confirmation_code": booked["confirmation_code"],
                              "detail": flight["airline"] + " " + flight["flight_id"],
                              "price_usd": booked["price_usd"], "fare": booked["fare"],
                              "completes": ["Book " + o + " to " + d]})

    # With the flights booked, every leg's seat map at once, then an aisle seat on each, or
    # any open seat in the cabin if no aisle seat is left.
    seat_maps = await asyncio.gather(*[get_seat_map({"flight_id": f["flight_id"]}) for f in flights])
    cabins = [[s for s in m["open_seats"] if s["cabin"] == fare] for m in seat_maps]
    aisles = [([s for s in cabin if "aisle" in s["features"]] or cabin)[0] for cabin in cabins]
    chosen = await asyncio.gather(*[
        select_seat({"confirmation_code": b["confirmation_code"], "flight_id": b["flight_id"],
                     "passenger_name": b["passenger_name"], "fare": b["fare"], "seat": seat["seat"]})
        for b, seat in zip(flights_booked, aisles)
    ])
    for b, seat in zip(flights_booked, chosen):
        await record_seat({"trip_id": trip_id, "confirmation_code": b["confirmation_code"], "seat": seat["seat"]})

    for (city, _, _, nights), hotel, booked in zip(stays, hotels, hotels_booked):
        await record_booking({"trip_id": trip_id, "kind": "hotel",
                              "confirmation_code": booked["confirmation_code"],
                              "detail": hotel["name"] + " " + hotel["hotel_id"],
                              "price_usd": hotel["price_per_night_usd"] * nights,
                              "completes": ["Book a hotel in " + city]})

    await set_trip_status({"trip_id": trip_id, "status": "booked"})
    return await read_trip_board()

asyncio.run(main())
"""


async def main(approvals: bool) -> None:
    storage = await config.payload_storage()
    client = await config.connect([AgentHarnessPlugin(large_payload_offload=storage)])
    policy = (
        ToolApprovalPolicy.allow_tools([*BOARD_TOOL_NAMES, *CHOICE_TOOL_NAMES])
        if approvals
        else ToolApprovalPolicy.dangerously_skip_all()
    )
    session_id = prefix_for(DEV_USER) + "preview-" + secrets.token_hex(3)
    await client.start_workflow(
        "MontyDynamicAgent",
        AgentConfig(approval_policy=policy),
        id=session_id,
        task_queue=config.TASK_QUEUE,
        execution_timeout=config.SESSION_TIMEOUT,
    )
    await AgentClient(temporal=client, workflow_id=session_id).submit_message(
        "run_script", {"script": SCRIPT}
    )
    base = os.environ.get("PREVIEW_BASE_URL", f"http://localhost:{os.environ.get('PORT', '8000')}")
    print(json.dumps({"session": session_id}))
    print(f"Open {base}/?s={session_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-approvals", action="store_true", help="run every call without asking")
    asyncio.run(main(approvals=not parser.parse_args().no_approvals))
