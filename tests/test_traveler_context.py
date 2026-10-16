from datetime import date

import pytest
from pydantic import ValidationError

from agent_harness_demo.monty.conversational_workflow import SYSTEM_INSTRUCTION, system_instruction
from agent_harness_demo.monty.models import TravelerContext


def test_the_prompt_ends_with_the_travelers_date():
    context = TravelerContext(today=date(2026, 12, 1), timezone="America/New_York")
    prompt = system_instruction(SYSTEM_INSTRUCTION, context)
    assert prompt.startswith(SYSTEM_INSTRUCTION)
    assert prompt.endswith(context.prompt_line())
    assert "Tuesday, December 1, 2026 in America/New_York" in prompt


def test_the_prompt_asks_for_gathered_calls_not_awaits_in_a_loop():
    assert "never `await` inside the loop" in SYSTEM_INSTRUCTION
    assert "no `return_exceptions`" in SYSTEM_INSTRUCTION


@pytest.mark.parametrize("timezone", ["not a zone", "America/New_York; drop", "../etc"])
def test_a_malformed_time_zone_is_refused(timezone):
    with pytest.raises(ValidationError):
        TravelerContext(today=date(2026, 12, 1), timezone=timezone)
