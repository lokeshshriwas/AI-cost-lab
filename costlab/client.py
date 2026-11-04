"""The one place that talks to the Claude API.

Every call goes through the record/replay cache. A cache miss in "replay" mode
is an error, and a real API call needs COSTLAB_ALLOW_PAID=1, so tests and CI
can never spend credit by accident.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from costlab.cache import ResponseCache
from costlab.pricing import PriceTable, Usage

PAID_FLAG = "COSTLAB_ALLOW_PAID"


class PaidCallNotAllowed(RuntimeError):
    pass


class CacheMiss(RuntimeError):
    pass


@dataclass(frozen=True)
class CallResult:
    model: str
    text: str
    stop_reason: str | None
    usage: Usage
    cost_usd: float
    latency_s: float
    from_cache: bool
    # True when the call went through the Message Batches API (priced at batch_multiplier).
    batch: bool = False


class BatchRequestFailed(RuntimeError):
    """One request inside a batch did not succeed (errored, canceled or expired)."""


class ModelClient:
    def __init__(
        self,
        cache: ResponseCache | None = None,
        prices: PriceTable | None = None,
        mode: str = "record",
        sdk_client: Any = None,
        cache_tag: str | None = None,
    ):
        if mode not in ("record", "replay"):
            raise ValueError("mode must be 'record' or 'replay'")
        self.cache = cache or ResponseCache()
        self.prices = prices or PriceTable.load()
        self.mode = mode
        self._sdk = sdk_client
        # A repeat tag gives every request a different cache key, so a tagged run makes fresh
        # calls (quality gate 4) while untagged keys, and their recorded answers, stay valid.
        self.cache_tag = cache_tag

    def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        system: str | list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
        **options: Any,
    ) -> CallResult:
        request: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if system is not None:
            request["system"] = system
        request.update(options)

        key = self._key(request)
        entry = self.cache.get(key)
        if entry is not None:
            return self._result(entry, from_cache=True)

        if self.mode == "replay":
            raise CacheMiss(f"No recorded response for {model} (key {key[:12]})")
        if os.environ.get(PAID_FLAG) != "1":
            raise PaidCallNotAllowed(f"Real API call blocked; set {PAID_FLAG}=1 for a paid run")

        entry = self._send(request)
        self.cache.put(key, entry)
        return self._result(entry, from_cache=False)

    def call_batch(
        self,
        requests: list[dict[str, Any]],
        *,
        poll_s: float = 30.0,
        timeout_s: float = 24 * 3600,
    ) -> list[CallResult | BatchRequestFailed]:
        """Send requests through the Message Batches API (50% price, results within 24 h).

        Each request is a full Messages request dict (model, messages, max_tokens, ...).
        Returns one item per request, in order: a CallResult, or a BatchRequestFailed for a
        request that did not succeed. Batch answers are cached under their own key, so a batch
        run and a normal run of the same prompt never replay each other's answers.
        """
        keys = [self._key({**r, "_batch": True}) for r in requests]
        out: list[CallResult | BatchRequestFailed | None] = [None] * len(requests)
        missing: dict[str, dict[str, Any]] = {}
        for i, (key, request) in enumerate(zip(keys, requests, strict=True)):
            entry = self.cache.get(key)
            if entry is not None:
                out[i] = self._result(entry, from_cache=True)
            else:
                missing[key] = request  # duplicates collapse: custom_id must be unique

        if missing:
            if self.mode == "replay":
                raise CacheMiss(f"{len(missing)} batch request(s) have no recorded response")
            if os.environ.get(PAID_FLAG) != "1":
                raise PaidCallNotAllowed(f"Real API call blocked; set {PAID_FLAG}=1 for a paid run")
            entries, failures = self._send_batch(missing, poll_s, timeout_s)
            for key, entry in entries.items():
                self.cache.put(key, entry)
            for i, key in enumerate(keys):
                if out[i] is not None:
                    continue
                if key in entries:
                    out[i] = self._result(entries[key], from_cache=False)
                else:
                    out[i] = BatchRequestFailed(failures.get(key, "missing from batch results"))
        return out  # type: ignore[return-value]

    def recent_batches(self, limit: int = 5) -> list[dict[str, Any]]:
        """The account's newest Message Batches (a free read, no tokens). For finding a batch
        that was submitted by a run that was interrupted before it collected the results."""
        out = []
        for i, b in enumerate(self._sdk_client().messages.batches.list(limit=limit)):
            if i >= limit:
                break
            counts = b.request_counts
            out.append(
                {
                    "id": b.id,
                    "status": b.processing_status,
                    "created_at": str(b.created_at),
                    "succeeded": counts.succeeded,
                    "processing": counts.processing,
                    "errored": counts.errored,
                }
            )
        return out

    def import_batch(self, batch_id: str, requests: list[dict[str, Any]]) -> int:
        """Cache the results of an already-finished batch, so they are not paid for twice.

        `requests` are the requests the batch was built from; results are matched by custom_id,
        which is each request's batch cache key. Returns how many answers were cached.
        """
        by_key = {self._key({**r, "_batch": True}): r for r in requests}
        sdk = self._sdk_client()
        if sdk.messages.batches.retrieve(batch_id).processing_status != "ended":
            raise RuntimeError(f"batch {batch_id} has not ended yet")
        cached = 0
        for item in sdk.messages.batches.results(batch_id):
            request = by_key.get(item.custom_id)
            if request is None or item.result.type != "succeeded":
                continue
            # The batch turnaround is unknown after an interruption; record 0, not a guess.
            entry = self._entry(request, item.result.message, 0.0)
            entry["batch"] = True
            self.cache.put(item.custom_id, entry)
            cached += 1
        return cached

    def _key(self, request: dict[str, Any]) -> str:
        # The tag is part of the key only; it is never sent to the API.
        if self.cache_tag is None:
            return self.cache.key(request)
        return self.cache.key({**request, "_tag": self.cache_tag})

    def _sdk_client(self):
        if self._sdk is None:
            import anthropic

            self._sdk = anthropic.Anthropic()
        return self._sdk

    def _send_batch(
        self, by_key: dict[str, dict[str, Any]], poll_s: float, timeout_s: float
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        sdk = self._sdk_client()
        start = time.perf_counter()
        # The cache key is a 64-character hex digest, a valid and unique custom_id.
        batch = sdk.messages.batches.create(
            requests=[{"custom_id": key, "params": request} for key, request in by_key.items()]
        )
        while batch.processing_status != "ended":
            if time.perf_counter() - start > timeout_s:
                raise TimeoutError(f"batch {batch.id} not finished after {timeout_s:.0f} s")
            time.sleep(poll_s)
            batch = sdk.messages.batches.retrieve(batch.id)
        # Per-request latency has no meaning in a batch; every answer took the batch turnaround.
        turnaround = time.perf_counter() - start

        entries: dict[str, dict[str, Any]] = {}
        failures: dict[str, str] = {}
        for item in sdk.messages.batches.results(batch.id):
            if item.result.type == "succeeded":
                entry = self._entry(by_key[item.custom_id], item.result.message, turnaround)
                entry["batch"] = True
                entries[item.custom_id] = entry
            else:
                failures[item.custom_id] = f"batch request {item.result.type}"
        return entries, failures

    def _send(self, request: dict[str, Any]) -> dict[str, Any]:
        sdk = self._sdk_client()
        start = time.perf_counter()
        response = sdk.messages.create(**request)
        return self._entry(request, response, time.perf_counter() - start)

    @staticmethod
    def _entry(request: dict[str, Any], response: Any, latency: float) -> dict[str, Any]:
        usage = response.usage
        return {
            # Price by the model we asked for; response.model can differ in form.
            "model": request["model"],
            "text": "".join(b.text for b in response.content if b.type == "text"),
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0,
                "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
            },
            "latency_s": round(latency, 3),
            # When the answer was paid for; `costlab spend` totals the cache by day (gate 5).
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    def _result(self, entry: dict[str, Any], from_cache: bool) -> CallResult:
        usage = Usage(**entry["usage"])
        batch = entry.get("batch", False)
        return CallResult(
            model=entry["model"],
            text=entry["text"],
            stop_reason=entry["stop_reason"],
            usage=usage,
            # Recomputed every time from stored tokens, so price changes need no re-run.
            cost_usd=self.prices.cost(entry["model"], usage, batch=batch),
            latency_s=entry["latency_s"],
            from_cache=from_cache,
            batch=batch,
        )
