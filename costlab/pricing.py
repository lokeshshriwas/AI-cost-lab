"""Turn token usage into dollars using the rates in prices.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PRICES = Path(__file__).resolve().parent.parent / "prices.yaml"
PER_MILLION = 1_000_000


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        """Whole prompt size: uncached + written to cache + read from cache."""
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens


class PriceTable:
    def __init__(self, models: dict[str, dict[str, float]], batch_multiplier: float | None = None):
        self._models = models
        self.batch_multiplier = batch_multiplier

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PRICES) -> PriceTable:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(data["models"], data.get("batch_multiplier"))

    def models(self) -> list[str]:
        return sorted(self._models)

    def cost(self, model: str, usage: Usage, batch: bool = False) -> float:
        dollars = self._standard_cost(model, usage)
        if batch:
            if self.batch_multiplier is None:
                raise KeyError("No batch_multiplier in prices.yaml; cannot price a batch call")
            dollars *= self.batch_multiplier
        return dollars

    def _standard_cost(self, model: str, usage: Usage) -> float:
        if model not in self._models:
            raise KeyError(f"No price for model {model!r}; add it to prices.yaml")
        rate = self._models[model]
        threshold = rate.get("long_context_threshold")
        if threshold is not None and usage.prompt_tokens > threshold:
            rate = rate["long"]

        dollars = (
            usage.input_tokens * rate["input"]
            + usage.output_tokens * rate["output"]
            + usage.cache_creation_input_tokens * rate["cache_write"]
            + usage.cache_read_input_tokens * rate["cache_read"]
        )
        return dollars / PER_MILLION
