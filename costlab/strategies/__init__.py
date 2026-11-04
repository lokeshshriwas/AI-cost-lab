"""Cost strategies. Each has `name` and `run(task, client) -> Result`, like `runner.Baseline`."""

from costlab.runner import Baseline
from costlab.strategies.caching import PromptCaching
from costlab.strategies.cascade import Cascade
from costlab.strategies.combined import Combined
from costlab.strategies.limits import LowEffort
from costlab.strategies.response_cache import ResponseCacheStrategy
from costlab.strategies.trimming import TrimContext

STRATEGIES = {
    "baseline": Baseline,
    "prompt-caching": PromptCaching,
    "trim-context": TrimContext,
    "low-effort": LowEffort,
    "cascade": Cascade,
    "response-cache": ResponseCacheStrategy,
    "caching+low-effort": Combined,
}

__all__ = [
    "STRATEGIES",
    "Baseline",
    "Cascade",
    "Combined",
    "LowEffort",
    "PromptCaching",
    "ResponseCacheStrategy",
    "TrimContext",
]
