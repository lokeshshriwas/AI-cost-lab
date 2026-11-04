"""Turn token usage into dollars using the rates in prices.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from costlab.paths import find

PER_MILLION = 1_000_000


def default_prices_path() -> Path:
    """The project folder's prices.yaml if there is one, else the bundled one."""
    path = find("prices.yaml")
    if path is None:
        raise FileNotFoundError("no prices.yaml in the project folder or the installed package")
    return path


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
    def load(cls, path: Path | str | None = None) -> PriceTable:
        path = default_prices_path() if path is None else Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
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
