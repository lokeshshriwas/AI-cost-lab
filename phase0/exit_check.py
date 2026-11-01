"""Phase 0 exit check: same prompt, a cheap and a strong model, tokens and cost side by side.

Try writing your own version first; this is the reference answer.

Run (PowerShell), it costs well under one cent of API credit:
    $env:COSTLAB_ALLOW_PAID = "1"
    .venv\\Scripts\\python phase0\\exit_check.py
    $env:COSTLAB_ALLOW_PAID = "0"
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from costlab.pricing import PriceTable, Usage  # noqa: E402

PROMPT = "In two sentences, explain why output tokens usually cost more than input tokens."
MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]


def main() -> None:
    load_dotenv()
    if os.environ.get("COSTLAB_ALLOW_PAID") != "1":
        sys.exit("This makes 2 real API calls. Set COSTLAB_ALLOW_PAID=1 to run it.")

    client = anthropic.Anthropic()
    prices = PriceTable.load()

    for model in MODELS:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            # Low effort keeps thinking short; thinking tokens are billed as output.
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": PROMPT}],
        )
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        answer = "".join(b.text for b in response.content if b.type == "text")
        cost = prices.cost(model, usage)

        print(f"\n=== {model} ===")
        print(answer.strip())
        print(f"tokens in={usage.input_tokens} out={usage.output_tokens}  cost=${cost:.6f}")


if __name__ == "__main__":
    main()
