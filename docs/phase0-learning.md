# Phase 0: Learning guide

Goal: enough understanding to make good decisions, not expertise. About 1 to 2 weeks at 1 to 2
hours a day. Cost: $0, apart from a fraction of a cent for the exit check.

Use **claude.ai chat** for questions while learning (it doesn't read your files, so it uses less
of your limit). Write what surprised you in the Notes section at the bottom; it becomes blog material.

## Checklist

### 1. Python basics (skip what you know)
- [ ] Virtual environments: `py -3.12 -m venv .venv`, activating, why each project has its own.
- [ ] `pip install -e ".[dev]"`: what editable installs and optional dependencies are.
- [ ] Functions, dataclasses, type hints. Read `costlab/pricing.py`; it uses all three.
- [ ] pytest: fixtures, `monkeypatch`, `tmp_path`. Read `tests/test_client.py`.

### 2. How the Claude API works
Docs home: https://platform.claude.com/docs
- [ ] Messages API: `model`, `messages`, `system`, `max_tokens`, `stop_reason`.
- [ ] **Input vs output tokens and how each is priced.** Pricing page:
      https://platform.claude.com/docs/en/about-claude/pricing
- [ ] Thinking and `effort`: thinking tokens are billed as output. Lower effort = fewer tokens.
- [ ] Prompt caching: prefix matching, cache writes (~1.25x input) vs reads (0.05x to 0.1x input).
- [ ] Batch API: 50% off, results within hours.
- [ ] Token counting endpoint: estimate cost before sending.
- [ ] Your $40 credit: https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers

### 3. Structured output
- [ ] JSON output with a schema (`output_config.format`), and why it beats "please reply in JSON".
- [ ] Pydantic models for validating what comes back.

### 4. Evals
- [ ] What a grader is: exact match, test-based, rubric/LLM judge. When each is trustworthy.
- [ ] Why a fixed task set is needed to compare two strategies fairly.
- [ ] Why "cost per successful task" beats "cost per call".

### 5. This project's code
- [ ] Read `costlab/client.py` top to bottom. Explain to yourself why a test can never spend money.
- [ ] Run the tests: `.venv\Scripts\python -m pytest -q` (all should pass, $0).

## Exit check

You can write a ~30-line script that calls a cheap and a strong Claude model with the same prompt,
prints the tokens used, and computes the cost.

1. Do the Console setup first (Phase 1 step 1 in `docs/PLAN.md`) so you have an API key in `.env`.
2. Try writing the script yourself.
3. Compare with the reference: `phase0/exit_check.py`. Run it (PowerShell):

```powershell
$env:COSTLAB_ALLOW_PAID = "1"; .venv\Scripts\python phase0\exit_check.py; $env:COSTLAB_ALLOW_PAID = "0"
```

4. Log the cost in `memory/SPEND.md`, and check the Console's Cost page shows about the same.

## Notes

(Write what surprised you here.)
