"""Run one process of the demo: `python -m agent_harness_demo web|worker`."""

import argparse
import asyncio
import os

parser = argparse.ArgumentParser(prog="agent_harness_demo")
parser.add_argument("role", choices=("web", "worker"))
args = parser.parse_args()

if args.role == "web":
    import uvicorn

    from .web import create_app

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
else:
    from .worker import run

    asyncio.run(run())
