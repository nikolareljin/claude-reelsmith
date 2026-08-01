"""Running renders concurrently.

Threads are the right primitive here even though this is CPU-heavy work: every
worker spends its life waiting on an ffmpeg subprocess, so the GIL is never the
bottleneck and threads avoid the cost of pickling state across processes.

Failures are collected rather than raised. One unreadable file in a folder of
fifty should not abandon the other forty-nine after an hour of encoding.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .notify import Notify


@dataclass
class JobOutcome:
    """What happened to one unit of work."""

    item: Any
    label: str
    ok: bool
    result: Any = None
    error: str = ""
    skipped: bool = False
    seconds: float = 0.0


@dataclass
class BatchReport:
    outcomes: list[JobOutcome] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def succeeded(self) -> list[JobOutcome]:
        return [o for o in self.outcomes if o.ok and not o.skipped]

    @property
    def skipped(self) -> list[JobOutcome]:
        return [o for o in self.outcomes if o.skipped]

    @property
    def failed(self) -> list[JobOutcome]:
        return [o for o in self.outcomes if not o.ok]

    def summary(self) -> str:
        bits = [f"{len(self.succeeded)} rendered"]
        if self.skipped:
            bits.append(f"{len(self.skipped)} already current")
        if self.failed:
            bits.append(f"{len(self.failed)} failed")
        bits.append(f"{self.seconds:.0f}s")
        return ", ".join(bits)


def run_batch(
    items: Sequence[Any],
    worker: Callable[[Any], Any],
    *,
    label: Callable[[Any], str],
    jobs: int = 1,
    is_skip: Callable[[Any], bool] | None = None,
) -> BatchReport:
    """Run ``worker`` over ``items`` with a bounded pool.

    ``is_skip`` is consulted before dispatch so up-to-date work costs nothing
    and is still reported.
    """
    report = BatchReport()
    started = time.monotonic()
    total = len(items)
    completed = 0
    lock = threading.Lock()

    pending: list[Any] = []
    for item in items:
        if is_skip and is_skip(item):
            report.outcomes.append(
                JobOutcome(item=item, label=label(item), ok=True, skipped=True)
            )
            Notify.info(f"· {label(item)} — already current")
        else:
            pending.append(item)

    if not pending:
        report.seconds = time.monotonic() - started
        return report

    def execute(item: Any) -> JobOutcome:
        nonlocal completed
        name = label(item)
        job_started = time.monotonic()
        try:
            value = worker(item)
        except Exception as exc:  # noqa: BLE001 - one failure must not stop the batch
            outcome = JobOutcome(
                item=item, label=name, ok=False,
                error=str(exc), seconds=time.monotonic() - job_started,
            )
        else:
            outcome = JobOutcome(
                item=item, label=name, ok=True, result=value,
                seconds=time.monotonic() - job_started,
            )
        with lock:
            completed += 1
            position = f"[{completed}/{total}]"
        if outcome.ok:
            Notify.ok(f"{position} {name} — {outcome.seconds:.0f}s")
        else:
            Notify.error(f"{position} {name} — failed")
            for line in outcome.error.splitlines()[:6]:
                Notify.plain(f"      {line}")
        return outcome

    workers = max(1, min(jobs, len(pending)))
    if workers == 1:
        for item in pending:
            report.outcomes.append(execute(item))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(execute, item) for item in pending]
            for future in concurrent.futures.as_completed(futures):
                report.outcomes.append(future.result())

    report.seconds = time.monotonic() - started
    return report
