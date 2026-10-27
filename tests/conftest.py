"""A throwaway redis-server for the whole test run, which agent events stream through."""

import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from temporal_agent_harness.harness.redis_event_stream import RedisEventStream

from agent_harness_demo import config as demo_config

_server: subprocess.Popen | None = None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def pytest_configure(config: pytest.Config) -> None:
    global _server
    binary = shutil.which("redis-server")
    if binary is None:
        raise pytest.UsageError("The tests need redis-server on PATH (brew install redis).")
    port = _free_port()
    _server = subprocess.Popen(
        [binary, "--port", str(port), "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    demo_config.REDIS_URL = f"redis://127.0.0.1:{port}"


def pytest_unconfigure(config: pytest.Config) -> None:
    if _server is not None:
        _server.terminate()
        _server.wait()


@pytest_asyncio.fixture(autouse=True)
async def event_stream(monkeypatch) -> AsyncIterator[RedisEventStream]:
    """A fresh backend per test: a Redis asyncio connection belongs to the event loop it was
    opened on, and each test runs on its own loop."""
    stream = RedisEventStream(demo_config.REDIS_URL)
    monkeypatch.setattr(demo_config, "EVENT_STREAM", stream)
    yield stream
    # The backend has no close of its own; it opens its connection on first use.
    if stream._redis is not None:
        await stream._redis.aclose()
