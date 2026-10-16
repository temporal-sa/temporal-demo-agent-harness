"""A quiet event stream still sends something often enough that proxies keep it open."""

import asyncio

from agent_harness_demo.web import KEEPALIVE, with_keepalive


async def frames(*items: tuple[float, bytes]):
    for delay, frame in items:
        await asyncio.sleep(delay)
        yield frame


async def collect(stream) -> list[bytes]:
    return [frame async for frame in stream]


async def test_a_quiet_stream_gets_keepalives_between_frames():
    got = await collect(with_keepalive(frames((0, b"a"), (0.35, b"b")), every=0.1))
    assert got[0] == b"a" and got[-1] == b"b"
    assert got[1:-1] and all(frame == KEEPALIVE for frame in got[1:-1])


async def test_a_busy_stream_passes_through_unchanged():
    got = await collect(with_keepalive(frames((0, b"a"), (0, b"b"), (0, b"c")), every=0.1))
    assert got == [b"a", b"b", b"c"]


async def test_closing_early_closes_the_underlying_stream():
    closed = asyncio.Event()

    async def endless():
        try:
            while True:
                await asyncio.sleep(1)
                yield b"never"
        finally:
            closed.set()

    stream = with_keepalive(endless(), every=0.05)
    assert await anext(stream) == KEEPALIVE
    await stream.aclose()
    assert closed.is_set()
