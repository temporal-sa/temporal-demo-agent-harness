"""A script asks the traveler to choose, the browser answers, and the script carries on.

`ask_traveler_to_choose` is a callback tool: the test plays the browser, reading the request
off the agent's event stream and answering it the way the demo view's cards do.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.contrib.workflow_streams import WorkflowStreamClient
from temporalio.worker import Worker

from temporal_agent_harness.harness.agent_client import AgentClient
from temporal_agent_harness.harness.agent_protocol import (
    SEND_AGENT_MESSAGE_UPDATE,
    TURN_EVENTS_TOPIC,
    AgentConfig,
    AgentEvent,
    AgentEventType,
    AgentMessage,
    AgentMessageReply,
)
from temporal_agent_harness.plugin import AgentHarnessPlugin

from agent_harness_demo.monty import activities
from agent_harness_demo.monty.workflow import MontyDynamicAgentWorkflow
from tests.temporal_env import start_workflow_environment

SCRIPT = """
import asyncio
async def main():
    found = await search_flights({"origin": "ATL", "destination": "ZRH", "date": "2026-12-21"})
    options: list[TripOption] = []
    for f in found["flights"][:2]:
        option: TripOption = {
            "option_id": f["flight_id"],
            "title": f["airline"] + " at " + f["departure_time"],
            "legs": [{"flight_id": f["flight_id"], "origin": "ATL", "destination": "ZRH",
                      "date": "2026-12-21", "airline": f["airline"],
                      "departure_time": f["departure_time"], "arrival_time": f["arrival_time"],
                      "stops": f["stops"]}],
            "fares": [{"level": x["level"], "total_usd": x["price_usd"]} for x in f["fares"]],
        }
        options.append(option)
    choice = await ask_traveler_to_choose({"question": "Which flight?", "options": options})
    return "picked " + str(choice["option_id"]) + " in " + str(choice["fare"])
asyncio.run(main())
"""


@pytest_asyncio.fixture
async def client_and_queue():
    env = await start_workflow_environment(data_converter=pydantic_data_converter)
    task_queue = f"monty-choice-test-{uuid.uuid4()}"
    async with Worker(
        env.client,
        task_queue=task_queue,
        workflows=[MontyDynamicAgentWorkflow],
        plugins=[AgentHarnessPlugin(tools=activities.ALL_TOOLS)],
    ):
        try:
            yield env.client, task_queue
        finally:
            await env.shutdown()


async def test_the_travelers_pick_comes_back_to_the_script(client_and_queue):
    client, task_queue = client_and_queue
    handle = await client.start_workflow(
        MontyDynamicAgentWorkflow.run,
        AgentConfig(),
        id=f"MontyDynamicAgent-{uuid.uuid4()}",
        task_queue=task_queue,
    )
    await handle.execute_update(
        SEND_AGENT_MESSAGE_UPDATE,
        AgentMessage(type="run_script", payload={"script": SCRIPT}),
        result_type=AgentMessageReply,
    )

    reply = None
    stream = WorkflowStreamClient.create(client, handle.id)
    async for item in stream.subscribe(
        topics=[TURN_EVENTS_TOPIC], from_offset=0, result_type=AgentEvent
    ):
        event = item.data.event
        if event.type == AgentEventType.CALLBACK_REQUESTED:
            options = event.tool_input["request"]["options"]
            assert len(options) == 2
            # Pick the second option in business, as a click on its fare button would.
            await AgentClient(temporal=client, workflow_id=handle.id).provide_callback_result(
                event.tool_id,
                result={"option_id": options[1]["option_id"], "fare": "business", "comment": None},
            )
        if event.type == AgentEventType.MESSAGE_HANDLER_END:
            reply = event.output.get("text")
        if event.type == AgentEventType.TURN_END:
            break

    assert reply is not None
    assert "picked FL-ATLZRH-20261221-002 in business" in reply


HOTEL_SCRIPT = """
import asyncio
async def main():
    found = await search_hotels({"city": "Zurich", "check_in": "2026-12-21", "check_out": "2026-12-24"})
    hotels: list[HotelOption] = []
    for h in found["hotels"][:2]:
        hotel: HotelOption = {"hotel_id": h["hotel_id"], "name": h["name"],
                              "neighborhood": h["neighborhood"], "star_rating": h["star_rating"],
                              "price_per_night_usd": h["price_per_night_usd"],
                              "total_usd": h["price_per_night_usd"] * 3}
        hotels.append(hotel)
    picked = await ask_traveler_to_choose_hotel({"question": "Where to stay?", "city": "Zurich",
                                                 "check_in": "2026-12-21", "check_out": "2026-12-24",
                                                 "options": hotels})
    return "staying at " + str(picked["hotel_id"])
asyncio.run(main())
"""


async def test_the_travelers_hotel_comes_back_to_the_script(client_and_queue):
    client, task_queue = client_and_queue
    handle = await client.start_workflow(
        MontyDynamicAgentWorkflow.run,
        AgentConfig(),
        id=f"MontyDynamicAgent-{uuid.uuid4()}",
        task_queue=task_queue,
    )
    await handle.execute_update(
        SEND_AGENT_MESSAGE_UPDATE,
        AgentMessage(type="run_script", payload={"script": HOTEL_SCRIPT}),
        result_type=AgentMessageReply,
    )

    reply = None
    picked = None
    stream = WorkflowStreamClient.create(client, handle.id)
    async for item in stream.subscribe(
        topics=[TURN_EVENTS_TOPIC], from_offset=0, result_type=AgentEvent
    ):
        event = item.data.event
        if event.type == AgentEventType.CALLBACK_REQUESTED:
            picked = event.tool_input["request"]["options"][1]["hotel_id"]
            await AgentClient(temporal=client, workflow_id=handle.id).provide_callback_result(
                event.tool_id, result={"hotel_id": picked, "comment": None}
            )
        if event.type == AgentEventType.MESSAGE_HANDLER_END:
            reply = event.output.get("text")
        if event.type == AgentEventType.TURN_END:
            break

    assert picked is not None
    assert reply is not None and f"staying at {picked}" in reply
