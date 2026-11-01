"""The one place that talks to the Claude API.

Every call goes through the record/replay cache. A cache miss in "replay" mode
is an error, and a real API call needs COSTLAB_ALLOW_PAID=1, so tests and CI
can never spend credit by accident.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
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


class ModelClient:
    def __init__(
        self,
        cache: ResponseCache | None = None,
        prices: PriceTable | None = None,
        mode: str = "record",
        sdk_client: Any = None,
    ):
        if mode not in ("record", "replay"):
            raise ValueError("mode must be 'record' or 'replay'")
        self.cache = cache or ResponseCache()
        self.prices = prices or PriceTable.load()
        self.mode = mode
        self._sdk = sdk_client

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

        key = self.cache.key(request)
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

    def _send(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._sdk is None:
            import anthropic

            self._sdk = anthropic.Anthropic()

        start = time.perf_counter()
        response = self._sdk.messages.create(**request)
        latency = time.perf_counter() - start

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
        }

    def _result(self, entry: dict[str, Any], from_cache: bool) -> CallResult:
        usage = Usage(**entry["usage"])
        return CallResult(
            model=entry["model"],
            text=entry["text"],
            stop_reason=entry["stop_reason"],
            usage=usage,
            # Recomputed every time from stored tokens, so price changes need no re-run.
            cost_usd=self.prices.cost(entry["model"], usage),
            latency_s=entry["latency_s"],
            from_cache=from_cache,
        )
