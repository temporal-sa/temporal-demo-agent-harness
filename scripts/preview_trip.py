"""Play a whole trip through the demo view without a model or an API key.

Starts a script-only Monty session (MontyDynamicAgent) as the local dev user and sends it one
script that plans a multi-city trip: searches run in parallel, then each booking lands on the
trip board. Every search and booking waits for approval in the demo view, as it would with
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

    # The searches of each kind run at once; each is its own durable Activity.
    flights_found = await asyncio.gather(
        *[search_flights({"origin": o, "destination": d, "date": day}) for o, d, day in legs]
    )
    hotels_found = await asyncio.gather(
        *[search_hotels({"city": c, "check_in": i, "check_out": out}) for c, i, out, _ in stays]
    )

    for (o, d, _), result in zip(legs, flights_found):
        flight = min(result["flights"], key=lambda f: f["price_usd"])
        booked = await book_flight({"flight_id": flight["flight_id"], "passenger_name": "Ada Lovelace"})
        await record_booking({"trip_id": trip_id, "kind": "flight",
                              "confirmation_code": booked["confirmation_code"],
                              "detail": flight["airline"] + " " + flight["flight_id"],
                              "price_usd": flight["price_usd"], "completes": ["Book " + o + " to " + d]})

    for (city, _, _, nights), result in zip(stays, hotels_found):
        hotel = min(result["hotels"], key=lambda h: h["price_per_night_usd"])
        booked = await book_hotel({"hotel_id": hotel["hotel_id"], "guest_name": "Ada Lovelace"})
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
        ToolApprovalPolicy.allow_tools(BOARD_TOOL_NAMES)
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
