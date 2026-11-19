"""The schema documents agents.toml points at match the agents they describe.

The web server reads each agent's init data from its committed schema document, not from the
agent's code, so a stale document would advertise (and enforce) the wrong start interface.
"""

from pathlib import Path

import pytest

from temporal_agent_kit.agent_schema import dump_agent_schema, load_agent_class

ZIGGY = Path(__file__).parent.parent / "agent_harness_demo" / "ziggy"


@pytest.mark.parametrize(
    "agent, schema_file",
    [
        (
            "agent_harness_demo.ziggy.conversational_workflow:ZiggyChatAgentWorkflow",
            "ZiggyChatAgent.schema.json",
        ),
        (
            "agent_harness_demo.ziggy.conversational_subagent_workflow:ZiggyChatSubagentWorkflow",
            "ZiggyChatSubagentAgent.schema.json",
        ),
    ],
)
def test_committed_schema_is_current(agent: str, schema_file: str):
    committed = (ZIGGY / schema_file).read_text()
    assert committed == dump_agent_schema(load_agent_class(agent)), (
        f"{schema_file} is stale: regenerate it with "
        f"`uv run temporal-agent-kit schema {agent} -o agent_harness_demo/ziggy/{schema_file}`"
    )
