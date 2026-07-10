"""Full Automation Engine v1.0 — autonomous publishing system.

The Automation Engine is designed to run **unattended for years**,
publishing one unique article with one unique image per execution.

Architecture
------------
::

    CLI (scripts/main.py)
      │
      ├─► run       — full pipeline (generate → image → publish)
      ├─► publish   — publish oldest pending article
      ├─► doctor    — health check
      ├─► metrics   — show metrics
      └─► retry     — retry failed articles


    pipeline.py
      │
      ├─► queue.py        — article locking / state management
      ├─► health.py       — pre-flight health verification
      ├─► metrics.py      — collect and store execution metrics
      ├─► notifier.py     — save execution reports to logs/reports/
      └─► recovery.py     — crash recovery on restart
"""

from __future__ import annotations

from automation.scheduler import Scheduler

__all__ = ["Scheduler"]
