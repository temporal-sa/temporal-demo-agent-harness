"""Conversational travel agent that gives the model Code Mode over the travel tools.

The user chats in plain text; a *model in the loop* converses to gather what it needs, then
**writes a Python script and runs it** to search and book flights/hotels, and replies in prose.
It does this through the harness Code Mode feature: :func:`agent.code_mode_tool` turns the travel
activity tools into a single ``run_travel_code`` tool that executes a model-authored script in a
sandbox, where each tool is an async host function the script calls. Every host call runs as a
durable, approval-gated activity, and the script can combine many with real control flow (loops,
``asyncio.gather`` concurrency).

The conversational front end is a Gemini Interactions tool-calling loop exposing that one Code
Mode tool. The workflow keeps the whole conversation and sends it on every call
(``InteractionConversation``), so multi-turn conversation works. The Code Mode tool advertises the
exact host-function signatures + result shapes in its own (generated) description, so the system
prompt only needs to set the persona and point the model at the tool.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel
from temporalio import workflow
from temporalio.contrib.workflow_streams import WorkflowStream
from temporalio.workflow import ActivityConfig

with workflow.unsafe.imports_passed_through():
    from google.genai._interactions.types import (
        FunctionCallStep,
    )
    from google.genai._interactions.types.function_result_step_param import (
        FunctionResultStepParam,
    )
    from google.genai.client import AsyncClient
    from temporal_agent_harness.ai_sdks.google_genai_plugin import (
        InteractionConversation,
        function_param,
        google_genai_client,
    )
    from temporal_agent_harness.harness import agent
    from temporal_agent_harness.harness.agent_protocol import (
        AgentConfig,
        MidTurn,
        TextMessage,
        TextReply,
        ToolApprovalPolicy,
    )
    from temporal_agent_harness.harness.agent_workflow import AgentWorkflowRunner

    from . import activities, choices, trip_board
    from .models import TravelerContext


SUPPORTED_MODELS = ("gemini-3.8-flash", "gemini-3.1-flash-lite")
DEFAULT_MODEL = SUPPORTED_MODELS[0]


class SetModel(BaseModel):
    """Which model this Monty session should use for subsequent turns."""

    # A Literal (not a bare str) so the choice is enforced rather than merely suggested:
    # pydantic rejects anything else at the update boundary, and the same constraint shows up
    # as an enum in this handler's `parameters` JSON schema — which is what lets a generic
    # client render a dropdown without knowing anything about Monty.
    model: Literal[SUPPORTED_MODELS]  # type: ignore[valid-type]


class PolicyUpdate(BaseModel):
    """Selected tool approval policy name."""

    new_policy: Literal["allow_safe", "strict", "dangerously_skip_all"]


# Shared with the subagent variant's prompt. Each host call is its own Activity, so calls a
# script gathers run in parallel; ones it awaits one by one take as long as all of them added
# up. The nested form is the one the sandbox's type checker accepts for mixed result types.
CONCURRENCY_GUIDANCE = """\
- Run every independent host call in a script at the same time. Never `await` one search and \
then the next: each call is a durable Activity, and the ones you gather run in parallel. Put \
calls that return the same type in one `asyncio.gather` and gather those groups together. The \
sandbox type-checks results, so a single gather that mixes flight and hotel calls fails before \
anything runs:
  flights, hotels = await asyncio.gather(
      asyncio.gather(search_flights({...}), search_flights({...})),
      asyncio.gather(search_hotels({...})),
  )
  outbound, inbound, stay = flights[0], flights[1], hotels[0]
  To compare many dates or airports, build the calls in the loop and gather them once; never \
`await` inside the loop:
  calls = [search_flights({...}) for day in days]
  found = await asyncio.gather(*calls)
  `asyncio.gather` takes no keyword arguments here, so there is no `return_exceptions`; gather \
the calls plainly rather than wrapping each one in try/except.
  Book independent choices the same way, once the traveler has picked them."""


# Shared with the subagent variant's prompt, like the guidance above.
BOOKING_GUIDANCE = """\
- Flights come in economy, premium, and business fares; ask which the traveler wants if they \
haven't said. Book the flight first, without a seat.
- Then ask about seats. Fetch `get_seat_map` for every booked leg at once and suggest one or \
two seats per leg that fit what the traveler said. Describe each seat from its `features`, \
drawbacks as well as perks, the way a good agent would: "14C is a bulkhead aisle seat with \
extra legroom, but there's no under-seat storage, so your bag goes overhead. Want it?" \
Mention any `extra_usd`. Only call `select_seat` once the traveler agrees, then `record_seat`."""


# Shared with the subagent variant's prompt, like the guidance above.
CHOICE_GUIDANCE = """\
- Whenever you offer the traveler two or more trip options, don't list them in prose. In the \
same script as the searches, build at most four options from the results and call \
`ask_traveler_to_choose` with your question and, for each option, its legs (flight_id, route, \
date, airline, times, stops) and the trip total at each fare. The traveler picks on cards in \
their browser, and the call returns their `Choice`: book that option at that fare, or, if \
`option_id` is None, read their `comment` and adjust.
- Hotels work the same way: for each city, call `ask_traveler_to_choose_hotel` with the city, \
the check-in and check-out dates, and at most four hotels, each with its nightly price and \
`total_usd` for the whole stay. Book the `hotel_id` it returns, or, if that is None, read \
the `comment` and adjust. Ask about one city per call.
- To find the picked option or hotel in your results, loop over them: the sandbox has no \
`next()` over a generator expression.
- Annotate what you build with the sandbox's types, or the type check rejects it:
  options: list[TripOption] = []
  option: TripOption = {"option_id": ..., "title": ..., "legs": [...], "fares": [...]}
  hotels: list[HotelOption] = []
  offer: HotelOption = {"hotel_id": ..., "name": ..., "neighborhood": ..., "star_rating": ..., \
"price_per_night_usd": ..., "total_usd": ...}"""


def system_instruction(base: str, context: TravelerContext | None) -> str:
    """The prompt for one session: the shared instructions, then the traveler's date.

    Without context, today's date comes from the Workflow clock, which replays identically."""
    context = context or TravelerContext(today=workflow.now().date())
    return f"{base}\n\n{context.prompt_line()}"

SYSTEM_INSTRUCTION = f"""\
You are a friendly travel-booking assistant. You help users search and book flights and \
hotels and assemble trip itineraries. You don't have these abilities directly — instead you \
write small async Python scripts and run them with the `run_travel_code` tool, which exposes the \
travel operations as async host functions your script calls. The tool's description gives the \
exact host-function signatures and result shapes — follow them; index results with normal Python.

How to behave:
- Converse naturally. Ask brief clarifying questions when you're missing something essential \
(origin/destination, dates, traveler name) — don't interrogate; make reasonable assumptions \
and state them.
- When you have enough to make progress, WRITE A SCRIPT and call `run_travel_code`. Keep each \
script focused (search, or book, or summarize) so you can react to results.
{CONCURRENCY_GUIDANCE}
{CHOICE_GUIDANCE}
{BOOKING_GUIDANCE}
- After a tool result, read it and reply to the user in plain, friendly prose — summarize \
options, prices, confirmations. You may run more scripts in follow-up turns as the \
conversation continues.
- Never invent flight/hotel ids or confirmation codes — only use ones returned by a script.

Keep the trip board current. The same script can call the board host functions — \
`open_trip`, `record_booking`, `complete_trip_tasks`, `add_trip_tasks`, `set_trip_status`, \
`read_trip_board` — and they are how the user watches you work. The board is not a summary you \
write at the end; it is the running state of the trip, so:
- `open_trip` as soon as you know which trip this is, BEFORE you search anything. Keep the \
`trip_id` it returns and use it for every later call (or pass "latest").
- In the SAME script that books something, `record_booking` it with the confirmation code the \
booking returned, and name the checklist items it finishes in `completes`. Never let the board \
show a booked flight next to an outstanding "book the flight".
- `complete_trip_tasks` as soon as a task is genuinely done, and `add_trip_tasks` the moment you \
find the trip needs something the plan did not have.
- `set_trip_status` to "booked" once nothing is left, or "cancelled" if the user calls it off.
- `read_trip_board` at the start of a follow-up request to recall where you left off.
Board calls are cheap and are not gated on the user's approval — there is nothing to approve \
about your own notes — so there is never a reason to batch them up or skip them."""


@agent.defn(name="MontyChatAgent")
class MontyChatAgentWorkflow:
    trip_board = agent.state(trip_board.TripBoard)

    @agent.init
    def __init__(self, config: AgentConfig, data: TravelerContext | None = None) -> None:
        self._instruction = system_instruction(SYSTEM_INSTRUCTION, data)
        self._runner = AgentWorkflowRunner(
            config,
            stream=WorkflowStream(),
            # Demo stance: require human approval for EVERY tool call that reaches the outside
            # world — both the `run_travel_code` tool and each travel host call the script makes
            # (search/book flights & hotels), since every call is dispatched through run_tool and
            # gated. The trip-board tools are allowed by name, and only those: they write to the
            # agent's own notes, so there is nothing for a human to approve, and gating them
            # would mean a click between every step and the board that is supposed to be showing
            # the steps. Choice cards are allowed too: asking the traveler is itself the human
            # step. Named rather than `allow_inherently_safe()`, which would also stop gating
            # the run-code tool itself and take the script review off the table.
            approval_policy_default=ToolApprovalPolicy.allow_tools(
                [*trip_board.BOARD_TOOL_NAMES, *choices.CHOICE_TOOL_NAMES]
            ),
        )
        self._model: str = DEFAULT_MODEL
        # The whole conversation, sent as the input of every model call (see
        # InteractionConversation for why it is not chained by interaction id).
        self._conversation = InteractionConversation()
        # The single model-facing tool: Code Mode over the travel tools. The model writes a
        # Python script that calls the travel operations as async host functions; each host call
        # runs as a durable, approval-gated activity via run_tool.
        self._code_tool = agent.code_mode_tool(
            # The travel tools plus the board tools, in one sandbox: a script can book a
            # flight and record it on the board without a round trip through the model, so
            # the board cannot drift from what was actually booked.
            [*activities.ALL_TOOLS, *trip_board.BOARD_TOOLS, *choices.CHOICE_TOOLS],
            name="run_travel_code",
            # Hidden from the model and from the generated stubs: the script names the
            # trip, never the state it lives in.
            injections={"board": self.trip_board},
        )
        # The Temporal-aware AsyncClient from the Gemini plugin; the runner is wired in so reply
        # text streams to the workflow stream as it is generated.
        self._gemini = google_genai_client(
            activity_config=ActivityConfig(
                start_to_close_timeout=timedelta(minutes=3),
            ),
            runner=self._runner,
        )

    @agent.accepts(mid_turn=MidTurn.ENQUEUE)
    async def ask(self, message: TextMessage) -> TextReply:
        """Chat with the travel assistant. Describe the trip you want (flights, hotels,
        dates, traveler name) in plain text; the assistant converses, writes and runs Python
        scripts against a simulated travel backend as needed, and replies with the results."""
        reply_text = await self._handle_chat_turn(self._gemini, message.text)
        return TextReply(text=reply_text)

    # ACCEPT: reconfiguring the session is not work, so it should not wait behind work. It
    # joins the open turn and applies immediately, which is the whole point of being able to
    # switch models while the agent is mid-conversation. model_callable=False keeps it off a
    # parent agent's generated toolset by default — choosing the model is an operator's call,
    # not something a driving model should do to its own child.
    @agent.accepts(mid_turn=MidTurn.ACCEPT, model_callable=False)
    async def set_model(self, message: SetModel) -> TextReply:
        """Set the model this session uses for subsequent turns. Takes effect on the next
        model call, so a turn already in flight finishes on the model it started with."""
        self._model = message.model
        return TextReply(text=f"Model set to **{message.model}**.")

    @agent.accepts(mid_turn=MidTurn.ACCEPT, model_callable=False)
    async def set_approval_policy(self, policy_update: PolicyUpdate) -> TextReply:
        """Update the agent's tool approval policy."""
        match policy_update.new_policy:
            case "allow_safe":
                updated_policy = ToolApprovalPolicy.allow_inherently_safe()
            case "strict":
                updated_policy = ToolApprovalPolicy.always_require_human_approval()
            case "dangerously_skip_all":
                updated_policy = ToolApprovalPolicy.dangerously_skip_all()
            case _:
                return TextReply(text=f"Unknown approval policy requested: {policy_update}")
        self._runner.set_approval_policy(updated_policy)
        return TextReply(text=f"Updated tool approval policy to: {policy_update}")

    # ------------------------------------------------------------------ chat loop

    async def _handle_chat_turn(self, gemini: AsyncClient, user_text: str) -> str:
        """Run one conversational turn: stream the model, dispatch any ``run_travel_code``
        calls, feed results back, and loop until the model replies with no further calls.

        The whole conversation goes out as the input of every call; see
        ``InteractionConversation`` for why it is not chained by interaction id."""
        tools = [function_param(self._code_tool)]
        self._conversation.add_user_text(user_text)
        while True:
            stream = await gemini.interactions.create(
                model=self._model,
                input=self._conversation.steps,
                system_instruction=self._instruction,
                tools=tools,
                stream=True,
            )
            reply = await self._conversation.read_reply(stream)
            if not reply.function_calls:
                return reply.text
            self._conversation.add_function_results(
                await asyncio.gather(*(self._run_one_tool(fc) for fc in reply.function_calls))
            )

    async def _run_one_tool(self, call: FunctionCallStep) -> FunctionResultStepParam:
        """Execute one ``run_travel_code`` call via ``run_tool`` and return its result.

        ``run_tool`` parks the call id so the script's host calls and the tool's own
        lifecycle events correlate with the streaming activity's ``tool_requested``."""
        try:
            if call.name != self._code_tool.__name__:
                raise ValueError(f"unknown tool: {call.name!r}")
            result = await self._runner.run_tool(
                call.id, self._code_tool, injections=None, **call.arguments
            )
            response: FunctionResultStepParam = {
                "type": "function_result",
                "call_id": call.id,
                "name": call.name,
                "result": str(result),
            }
            if call.signature:
                response["signature"] = call.signature
            return response
        except Exception as e:
            response = {
                "type": "function_result",
                "call_id": call.id,
                "name": call.name,
                "result": str(e),
                "is_error": True,
            }
            if call.signature:
                response["signature"] = call.signature
            return response
