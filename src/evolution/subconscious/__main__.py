import argparse
import asyncio
import sys

from evolution.subconscious.common import bootstrap
from evolution.subconscious.dream import run_dream
from evolution.subconscious.pray import run_pray


def main(argv: list[str] | None = None) -> None:
    bootstrap()
    parser = argparse.ArgumentParser(description="Jarvis subconscious evolution jobs")
    parser.add_argument(
        "command",
        choices=["pray", "dream", "all"],
        help="Run pray (2 AM), dream (3 AM), or both sequentially (debug)",
    )
    args = parser.parse_args(argv)

    if args.command == "pray":
        asyncio.run(run_pray())
    elif args.command == "dream":
        asyncio.run(run_dream())
    elif args.command == "all":
        asyncio.run(run_pray())
        asyncio.run(run_dream())


if __name__ == "__main__":
    main(sys.argv[1:])
