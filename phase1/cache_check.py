"""Phase 1 exit check: the same request twice through ModelClient; the second must come from cache.

The first run makes 1 real call (well under one cent). Every later run makes 0 calls,
because the response is already recorded in cache/.

Run (PowerShell):
    $env:COSTLAB_ALLOW_PAID = "1"
    .venv\\Scripts\\python phase1\\cache_check.py
    $env:COSTLAB_ALLOW_PAID = "0"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from costlab import ModelClient  # noqa: E402

MODEL = "claude-haiku-5-5"
MESSAGES = [{"role": "user", "content": "Reply with exactly: cache check ok"}]


def main() -> None:
    load_dotenv()
    client = ModelClient()

    first = client.call(MODEL, MESSAGES, max_tokens=256, output_config={"effort": "low"})
    second = client.call(MODEL, MESSAGES, max_tokens=256, output_config={"effort": "low"})

    for label, result in (("first ", first), ("second", second)):
        source = "cache" if result.from_cache else "API (paid)"
        print(
            f"{label}: from {source:10}  in={result.usage.input_tokens} "
            f"out={result.usage.output_tokens}  cost=${result.cost_usd:.6f}  "
            f"{result.text.strip()!r}"
        )

    if not second.from_cache:
        sys.exit("FAIL: the second call was not served from the cache")
    real_cost = 0.0 if first.from_cache else first.cost_usd
    print(f"PASS: second call came from the cache. Credit used this run: ${real_cost:.6f}")


if __name__ == "__main__":
    main()
