"""Blogger AI Publisher Pro — CLI entry point.

Supports commands:

    python scripts/main.py run       Full pipeline (image + publish)
    python scripts/main.py publish   Publish next pending article
    python scripts/main.py doctor    Health check
    python scripts/main.py metrics   Show system metrics
    python scripts/main.py retry     Retry failed articles

Examples::

    # Run one full cycle
    python scripts/main.py run

    # Check system health
    python scripts/main.py doctor

    # Show metrics
    python scripts/main.py metrics
"""

from __future__ import annotations

import sys
from typing import NoReturn

from automation.scheduler import Scheduler
from config.logging import setup_logging
from database.database import close_connection

log = setup_logging()


def get_command() -> str:
    """Read the command from CLI arguments.

    Returns:
        Command string.  Defaults to ``"run"``.
    """
    if len(sys.argv) < 2:
        return "run"

    cmd = sys.argv[1].lower()
    valid = {"run", "publish", "doctor", "metrics", "retry"}
    return cmd if cmd in valid else "run"


def main() -> NoReturn:
    """CLI entry point."""
    command = get_command()
    log.info("Blogger AI Publisher Pro v1.0 — Command: %s", command)

    scheduler = Scheduler()
    exit_code = scheduler.run_command(command)
    close_connection()

    log.info("Exiting with code %d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
