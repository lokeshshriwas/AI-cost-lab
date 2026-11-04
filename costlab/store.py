"""SQLite results store. Every run and every task result is written here; reports read from it."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from costlab.client import CallResult
from costlab.models import Result
from costlab.pricing import Usage

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    workload    TEXT    NOT NULL,
    strategy    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    tasks_hash  TEXT    NOT NULL,
    task_count  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    run_id   INTEGER NOT NULL REFERENCES runs(id),
    task_id  TEXT    NOT NULL,
    passed   INTEGER NOT NULL,
    output   TEXT    NOT NULL,
    error    TEXT,
    calls    TEXT    NOT NULL,
    PRIMARY KEY (run_id, task_id)
);
"""


class ResultStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> ResultStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def save_run(
        self,
        *,
        workload: str,
        strategy: str,
        model: str,
        tasks_hash: str,
        results: list[Result],
    ) -> int:
        created = datetime.now(UTC).isoformat(timespec="seconds")
        with self._db:
            cur = self._db.execute(
                "INSERT INTO runs (created_at, workload, strategy, model, tasks_hash, task_count)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (created, workload, strategy, model, tasks_hash, len(results)),
            )
            run_id = cur.lastrowid
            self._db.executemany(
                "INSERT INTO results (run_id, task_id, passed, output, error, calls)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        r.task_id,
                        int(r.passed),
                        r.output,
                        r.error,
                        json.dumps(
                            [
                                {
                                    "model": c.model,
                                    "stop_reason": c.stop_reason,
                                    "usage": {
                                        "input_tokens": c.usage.input_tokens,
                                        "output_tokens": c.usage.output_tokens,
                                        "cache_creation_input_tokens": (
                                            c.usage.cache_creation_input_tokens
                                        ),
                                        "cache_read_input_tokens": (
                                            c.usage.cache_read_input_tokens
                                        ),
                                    },
                                    "latency_s": c.latency_s,
                                    "from_cache": c.from_cache,
                                    "batch": c.batch,
                                }
                                for c in r.calls
                            ]
                        ),
                    )
                    for r in results
                ],
            )
        return run_id

    def latest_runs(self) -> list[dict]:
        """The newest run for each (workload, strategy, model): one row per table line."""
        rows = self._db.execute(
            "SELECT r.id, r.workload, r.strategy, r.model, r.tasks_hash, r.task_count"
            " FROM runs r JOIN (SELECT MAX(id) AS id FROM runs"
            "   GROUP BY workload, strategy, model) latest ON r.id = latest.id"
            " ORDER BY r.workload, r.strategy, r.model"
        ).fetchall()
        keys = ("id", "workload", "strategy", "model", "tasks_hash", "task_count")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def load_results(self, run_id: int) -> list[Result]:
        run = self._db.execute(
            "SELECT workload, strategy FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if run is None:
            raise KeyError(f"no run with id {run_id}")
        workload, strategy = run
        rows = self._db.execute(
            "SELECT task_id, passed, output, error, calls FROM results"
            " WHERE run_id = ? ORDER BY task_id",
            (run_id,),
        ).fetchall()
        out = []
        for task_id, passed, output, error, calls_json in rows:
            calls = [
                CallResult(
                    model=c["model"],
                    text="",  # the reply is stored once, in results.output
                    stop_reason=c["stop_reason"],
                    usage=Usage(**c["usage"]),
                    cost_usd=0.0,  # not used: cost is recomputed from tokens on read
                    latency_s=c["latency_s"],
                    from_cache=c["from_cache"],
                    batch=c.get("batch", False),  # runs saved before batch support had none
                )
                for c in json.loads(calls_json)
            ]
            out.append(Result(task_id, workload, strategy, output, bool(passed), calls, error))
        return out
