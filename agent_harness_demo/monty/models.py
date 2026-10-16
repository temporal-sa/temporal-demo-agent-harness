"""Message and start types for the Monty agents.

NB: no ``from __future__ import annotations`` here — these cross Temporal's pydantic
converter, and stringized annotations leave the discriminated-union machinery "not fully
defined". Keep annotations concrete.
"""

from datetime import date

from pydantic import BaseModel, Field


class RunScript(BaseModel):
    """A Python script to run in the sandbox for this turn.

    The ``run_script`` operation's description documents the full sandbox contract — the async
    script structure, the concurrency rules, and the exact host-function signatures and result
    shapes the ``script`` may call. A type/syntax/runtime error in the script is reported as the
    reply text (a bad script is normal input, not a failure)."""

    script: str


class TravelerContext(BaseModel):
    """Where the traveler is in time, sent once when a conversation starts.

    A model only knows the date it was trained up to, so without this it plans trips in the
    past. The demo view sends the traveler's own date and time zone; a session started
    without it falls back to the Workflow's clock, in UTC."""

    today: date = Field(description="The traveler's local date when the conversation started.")
    timezone: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$",
        description="The traveler's IANA time zone, such as America/New_York.",
    )

    def prompt_line(self) -> str:
        where = f" in {self.timezone}" if self.timezone else ""
        return (
            f"Today is {self.today:%A, %B} {self.today.day}, {self.today.year}{where}. Plan from this "
            "date: never search dates in the past, and read a date the traveler gives without a "
            "year as the next one to come."
        )
