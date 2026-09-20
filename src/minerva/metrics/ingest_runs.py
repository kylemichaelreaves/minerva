"""One record per source per ingest run.

Deliberately NOT `pipeline_runs`: that table is keyed (lang, backend, model)
and holds histograms, while a source has no language, no engine and no model,
and one elapsed per run is a scalar rather than a distribution. Sharing the
table would make `count` mean two different things depending on the row.

Nothing here crosses a process boundary. `ingest/parallel.py`'s workers
already return `elapsed`, `count`, `skipped` and `error` to the orchestrator,
which already reads them to print `timing: ingest:<id>`. The parent writes.
"""

from __future__ import annotations

import dataclasses
import secrets
import time


@dataclasses.dataclass(frozen=True, slots=True)
class IngestRun:
    """One source's outcome in one invocation.

    `status` exists because a skipped source returns `elapsed=0`, and stored
    without it that reads as a source which suddenly became instant — the same
    not-measured/measured-zero confusion the request layer had to fix twice.
    It also makes "when did this source stop being ingested" answerable, which
    is the more common question in practice.
    """

    at: float
    run_id: str
    source_id: str
    status: str            # ok | skipped | failed
    elapsed_ms: float
    chunks: int
    error: str | None = None





class IngestRunLog:
    """Collects one invocation's per-source outcomes.

    Passed into whichever ingest path runs, so the sequential and parallel
    paths feed the same recorder. `--jobs` defaults to 1, so the SEQUENTIAL
    path is the default one — instrumenting only the parallel path would mean
    the ordinary invocation records nothing, silently.

    Recording is unconditional and does not follow `--timing`. That flag
    controls the stderr print; a history assembled only from runs where
    someone remembered a flag is not a history.
    """

    __slots__ = ("_rows", "run_id")

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or secrets.token_hex(8)
        self._rows: list[IngestRun] = []

    def record(
        self,
        source_id: str,
        *,
        status: str,
        elapsed_ms: float,
        chunks: int,
        error: str | None = None,
        at: float | None = None,
    ) -> None:
        self._rows.append(
            IngestRun(
                at=time.time() if at is None else at,
                run_id=self.run_id,
                source_id=source_id,
                status=status,
                elapsed_ms=elapsed_ms,
                chunks=chunks,
                error=error,
            )
        )

    def rows(self) -> list[IngestRun]:
        return list(self._rows)


__all__ = ["IngestRun", "IngestRunLog"]
