"""`costlab estimate`: what one prompt would cost on each model, before sending it.

Input tokens are counted exactly (the free count_tokens endpoint, per model: models tokenize
differently) or, offline, approximated at ~4 characters per token. Output length cannot be
known in advance, so it is an assumption the caller passes and the result repeats.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass

from costlab.pricing import PriceTable, Usage

# Only for --offline. Measured on this benchmark's 130 prompts against the recorded Haiku 5.5
# token counts (2026-11-04): median 2.34 chars/token on extraction, 2.60 on Q&A, 2.29 on code
# (range 2.03-2.79). The common "4 characters per token" rule undercounted a Q&A prompt by 35%.
CHARS_PER_TOKEN = 2.5


@dataclass(frozen=True)
class Estimate:
    model: str
    input_tokens: int
    output_tokens: int  # assumed, not measured
    exact: bool  # True when input_tokens came from count_tokens
    cost_usd: float
    batch_cost_usd: float | None  # None when prices.yaml has no batch_multiplier

    def as_dict(self) -> dict:
        return asdict(self)


def approx_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def estimate(
    prompt: str,
    models: list[str],
    prices: PriceTable,
    output_tokens: int,
    count: Callable[[str, str], int] | None = None,
) -> list[Estimate]:
    """One Estimate per model, cheapest first. `count(model, prompt)` gives exact input tokens;
    without it the offline approximation is used."""
    out = []
    for model in models:
        tokens = count(model, prompt) if count is not None else approx_tokens(prompt)
        usage = Usage(input_tokens=tokens, output_tokens=output_tokens)
        out.append(
            Estimate(
                model=model,
                input_tokens=tokens,
                output_tokens=output_tokens,
                exact=count is not None,
                cost_usd=prices.cost(model, usage),
                batch_cost_usd=(
                    prices.cost(model, usage, batch=True)
                    if prices.batch_multiplier is not None
                    else None
                ),
            )
        )
    return sorted(out, key=lambda e: e.cost_usd)


def format_estimates(estimates: list[Estimate]) -> str:
    exact = all(e.exact for e in estimates)
    lines = [
        "| Model | Input tokens | Output tokens (assumed) | Cost per call | Batch "
        "| Per 1,000 calls |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for e in estimates:
        batch = "n/a" if e.batch_cost_usd is None else f"${e.batch_cost_usd:.6f}"
        lines.append(
            f"| {e.model} | {e.input_tokens:,}{'' if e.exact else ' ~'} | {e.output_tokens:,} "
            f"| ${e.cost_usd:.6f} | {batch} | ${e.cost_usd * 1000:.2f} |"
        )
    lines.append("")
    lines.append(
        "Input tokens counted exactly (count_tokens)."
        if exact
        else f"~ Input tokens approximated offline (1 per {CHARS_PER_TOKEN:g} characters, "
        "measured on this benchmark; expect +/-15%). Drop --offline for exact counts."
    )
    lines.append(
        "Output tokens are an assumption (--output-tokens); thinking tokens count as output."
    )
    return "\n".join(lines)
