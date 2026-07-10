"""Application-wide logging configuration.

Logs are written to both a rotating file (``logs/app.log``) and the
console (stdout).  The log level and output format are controlled via
:mod:`config.settings`.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import NoReturn

from config.settings import LOG_DIR, LOG_FILE, LOG_FORMAT, LOG_DATE_FORMAT

# ---------------------------------------------------------------------------
# Module-level references (populated by setup_logging)
# ---------------------------------------------------------------------------
_logger: logging.Logger | None = None


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
) -> logging.Logger:
    """Configure the root logger with file + console handlers.

    The file handler writes to ``log_file`` (or ``settings.LOG_FILE``) with
    a rotating policy (5 MB max, 3 backups).  The console handler writes to
    stdout.

    Args:
        level:     Logging level (e.g. ``logging.DEBUG``).
        log_file:  Explicit log file path; defaults to ``LOG_FILE``.

    Returns:
        The configured root :class:`~logging.Logger`.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any pre-existing handlers so calls are idempotent.
    root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # --- File handler (rotating) ---
    target_file = log_file or LOG_FILE
    target_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=str(target_file),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # --- Console handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    global _logger  # noqa: PLW0603
    _logger = root
    root.info("Logging initialised — writing to %s", target_file)
    return root


def get_logger(name: str = __name__) -> logging.Logger:
    """Return the root logger if it exists, otherwise configure + return it.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        A :class:`~logging.Logger` instance.
    """
    if _logger is None:
        return setup_logging()
    return logging.getLogger(name)


def shutdown_logging() -> None:
    """Flush and shut down all logging handlers cleanly."""
    logging.shutdown()


def main() -> NoReturn:
    """Quick CLI test: ``python -m config.logging``."""
    setup_logging()
    log = get_logger(__name__)
    log.debug("Debug message (hidden at INFO level)")
    log.info("Info message — visible")
    log.warning("Warning message")
    log.error("Error message")
    log.critical("Critical message")
    print(f"\nLog file written to: {LOG_FILE}")
    sys.exit(0)


if __name__ == "__main__":
    main()
