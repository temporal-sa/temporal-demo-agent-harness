# ABOUTME: End-to-end test for the Ziggy dynamic agent against the time-skipping test
# server. Sends a RunScript whose script calls BOTH host functions (each backed by a
# durable activity) and asserts the reply carries the script's stdout + final value.
#
# This doubles as the experiment's key check: it runs under the DEFAULT (sandboxed)
# workflow runner, so a pass means the pydantic-monty interpreter both imports through
# the Temporal sandbox AND drives external async host functions across activity awaits.
#
# Run with: uv run pytest tests/ziggy/test_workflow.py -v

from __future__ import annotations

import uuid

import pytest_asyncio
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from tests.temporal_env import start_workflow_environment
from temporalio.worker import Worker

from temporal_agent_harness.harness.agent_protocol import (
    SEND_AGENT_MESSAGE_UPDATE,
    AgentConfig,
    AgentEvent,
    AgentEventType,
    AgentMessage,
    AgentMessageReply,
)

from temporal_agent_harness.plugin import AgentHarnessPlugin

from agent_harness_demo import config
from agent_harness_demo.ziggy import activities
from agent_harness_demo.ziggy.workflow import ZiggyDynamicAgentWorkflow


@pytest_asyncio.fixture
async def client_and_queue():
    env = await start_workflow_environment(
        data_converter=pydantic_data_converter
    )
    task_queue = f"ziggy-agent-test-{uuid.uuid4()}"
    # Mirrors agent_harness_demo/worker.py: the harness plugin registers the travel tools' activity
    # bodies. (Passed to the Worker rather than the
    # client because the test env's client is already connected.)
    async with Worker(
        env.client,
        task_queue=task_queue,
        workflows=[ZiggyDynamicAgentWorkflow],
        plugins=[AgentHarnessPlugin(tools=activities.ALL_TOOLS, event_stream=config.EVENT_STREAM)],
    ):
        try:
            yield env.client, task_queue
        finally:
            await env.shutdown()


async def _reply_text(client: Client, workflow_id: str) -> str:
    reply: str | None = None
    async for item in config.EVENT_STREAM.subscribe(client, workflow_id, from_offset=0):
        envelope: AgentEvent = item.data
        if envelope.event.type == AgentEventType.MESSAGE_HANDLER_END:
            # run_script returns a TextReply; read its text off the output dict.
            reply = envelope.event.output.get("text")
        if envelope.event.type == AgentEventType.TURN_END:
            break
    assert reply is not None, "turn ended without a reply"
    return reply


async def test_script_calls_host_functions(client_and_queue):
    client, task_queue = client_and_queue
    handle = await client.start_workflow(
        ZiggyDynamicAgentWorkflow.run,
        AgentConfig(),
        id=f"ZiggyDynamicAgent-{uuid.uuid4()}",
        task_queue=task_queue,
    )

    # Concurrently search flights AND hotels (one gathered batch → two durable activities
    # in flight at once), then book the cheapest flight in premium and choose a premium seat
    # from its seat map — exercising the async batch driver end-to-end: a multi-call
    # concurrent batch followed by dependent sequential calls. Host functions are ASYNC and
    # must be awaited.
    script = (
        "import asyncio\n"
        "async def main():\n"
        "    flights, hotels = await asyncio.gather(\n"
        '        search_flights({"origin": "SFO", "destination": "JFK", "date": "2026-07-01"}),\n'
        '        search_hotels({"city": "New York", "check_in": "2026-07-01", "check_out": "2026-07-05"}),\n'
        "    )\n"
        '    cheapest = min(flights["flights"], key=lambda f: f["price_usd"])\n'
        '    flight = await book_flight({"flight_id": cheapest["flight_id"], "passenger_name": "Ada Lovelace",\n'
        '                                "fare": "premium"})\n'
        '    seats = await get_seat_map({"flight_id": cheapest["flight_id"]})\n'
        '    seat = [s for s in seats["open_seats"] if s["cabin"] == "premium"][0]\n'
        '    chosen = await select_seat({"confirmation_code": flight["confirmation_code"],\n'
        '                                "flight_id": flight["flight_id"], "passenger_name": "Ada Lovelace",\n'
        '                                "fare": "premium", "seat": seat["seat"]})\n'
        "    print(f\"airline={cheapest['airline']} hotels={len(hotels['hotels'])}\")\n"
        '    return [flight, chosen]\n'
        "asyncio.run(main())"
    )
    await handle.execute_update(
        SEND_AGENT_MESSAGE_UPDATE,
        AgentMessage(type="run_script", payload={"script": script}),
        result_type=AgentMessageReply,
    )

    reply = await _reply_text(client, handle.id)
    # The reply carries the printed airline line plus the booking (final expression).
    assert "airline=" in reply
    assert "'fare': 'premium'" in reply
    assert "'passenger_name': 'Ada Lovelace'" in reply
    assert "'features': [" in reply  # the chosen seat comes back described
    assert "AIR-" in reply  # flight confirmation code prefix


async def test_script_syntax_error_is_reported(client_and_queue):
    client, task_queue = client_and_queue
    handle = await client.start_workflow(
        ZiggyDynamicAgentWorkflow.run,
        AgentConfig(),
        id=f"ZiggyDynamicAgent-{uuid.uuid4()}",
        task_queue=task_queue,
    )
    await handle.execute_update(
        SEND_AGENT_MESSAGE_UPDATE,
        AgentMessage(type="run_script", payload={"script": "def ("}),
        result_type=AgentMessageReply,
    )

    reply = await _reply_text(client, handle.id)
    assert "Script error" in reply


async def _run_script_reply(client, task_queue, script: str) -> str:
    handle = await client.start_workflow(
        ZiggyDynamicAgentWorkflow.run,
        AgentConfig(),
        id=f"ZiggyDynamicAgent-{uuid.uuid4()}",
        task_queue=task_queue,
    )
    await handle.execute_update(
        SEND_AGENT_MESSAGE_UPDATE,
        AgentMessage(type="run_script", payload={"script": script}),
        result_type=AgentMessageReply,
    )
    return await _reply_text(client, handle.id)


def _select_seat_script(seat_cabin: str, claimed_fare: str) -> str:
    """Books economy on the first SFO→JFK flight, then asks for a `seat_cabin` seat on it,
    giving the booking's fare as `claimed_fare`."""
    return (
        "import asyncio\n"
        "async def main():\n"
        '    found = await search_flights({"origin": "SFO", "destination": "JFK", "date": "2026-07-01"})\n'
        '    flight_id = found["flights"][0]["flight_id"]\n'
        '    booked = await book_flight({"flight_id": flight_id, "passenger_name": "Ada Lovelace"})\n'
        '    seats = await get_seat_map({"flight_id": flight_id})\n'
        f'    seat = [s for s in seats["open_seats"] if s["cabin"] == "{seat_cabin}"][0]\n'
        '    return await select_seat({"confirmation_code": booked["confirmation_code"],\n'
        '                              "flight_id": flight_id, "passenger_name": "Ada Lovelace",\n'
        f'                              "fare": "{claimed_fare}", "seat": seat["seat"]}})\n'
        "asyncio.run(main())"
    )


async def test_a_seat_outside_the_fares_cabin_is_refused(client_and_queue):
    client, task_queue = client_and_queue
    script = _select_seat_script(seat_cabin="business", claimed_fare="economy")
    reply = await _run_script_reply(client, task_queue, script)
    assert "is in business, not economy" in reply


async def test_a_seat_for_a_booking_that_does_not_match_is_refused(client_and_queue):
    client, task_queue = client_and_queue
    script = _select_seat_script(seat_cabin="premium", claimed_fare="premium")
    reply = await _run_script_reply(client, task_queue, script)
    assert "use the details book_flight returned" in reply


async def test_streaming_leaves_no_signals_or_updates_in_history(client_and_queue):
    # Events go to Redis, so a whole turn (script, tool calls, trip board changes) leaves only
    # the message update and the activities in the agent's history: no WorkflowStream publish
    # Signals from activities and no poll Updates from readers.
    client, task_queue = client_and_queue
    handle = await client.start_workflow(
        ZiggyDynamicAgentWorkflow.run,
        AgentConfig(),
        id=f"ZiggyDynamicAgent-{uuid.uuid4()}",
        task_queue=task_queue,
    )
    await handle.execute_update(
        SEND_AGENT_MESSAGE_UPDATE,
        AgentMessage(type="run_script", payload={"script": _select_seat_script("premium", "economy")}),
        result_type=AgentMessageReply,
    )
    await _reply_text(client, handle.id)

    signals, updates = [], []
    async for event in handle.fetch_history_events():
        if event.HasField("workflow_execution_signaled_event_attributes"):
            signals.append(event.workflow_execution_signaled_event_attributes.signal_name)
        if event.HasField("workflow_execution_update_accepted_event_attributes"):
            attributes = event.workflow_execution_update_accepted_event_attributes
            updates.append(attributes.accepted_request.input.name)
    assert signals == []
    assert updates == [SEND_AGENT_MESSAGE_UPDATE]
