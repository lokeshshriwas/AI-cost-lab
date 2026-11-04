import json
from pathlib import Path

import pytest

from costlab import CallResult, PriceTable, Usage
from costlab.cli import main
from costlab.models import Task, load_tasks, summarize
from costlab.report import build_comparison
from costlab.runner import Baseline, run_strategy
from costlab.store import ResultStore
from costlab.strategies import Cascade, LowEffort, PromptCaching, TrimContext
from costlab.strategies.caching import cached_content, split_prefix
from costlab.strategies.cascade import looks_valid
from costlab.strategies.trimming import trim_prompt

ROOT = Path(__file__).resolve().parent.parent / "workloads"
QA = load_tasks(ROOT / "qa" / "tasks.jsonl")
EXTRACTION = load_tasks(ROOT / "extraction" / "tasks.jsonl")
CODEFIX = load_tasks(ROOT / "codefix" / "tasks.jsonl")
CHEAP, STRONG = "claude-haiku-5-5", "claude-sonnet-5-5"


def text_of(content) -> str:
    return content if isinstance(content, str) else "".join(b["text"] for b in content)


class CapturingClient:
    """Records every request; replies via `answer(model, prompt_text)`. Never calls the API."""

    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    def call(self, model, messages, *, max_tokens=1024, **options):
        self.requests.append({"model": model, "messages": messages, "options": options})
        return CallResult(
            model=model,
            text=self.answer(model, text_of(messages[0]["content"])),
            stop_reason="end_turn",
            usage=Usage(input_tokens=1_000, output_tokens=100),
            cost_usd=0.0,
            latency_s=0.1,
            from_cache=False,
        )


# ---- baseline must not drift (its cached replies are keyed on the exact request) ----


def test_baseline_request_is_unchanged():
    client = CapturingClient(lambda m, p: "x")
    Baseline(CHEAP).run(QA[0], client)
    assert client.requests == [
        {"model": CHEAP, "messages": [{"role": "user", "content": QA[0].input}], "options": {}}
    ]


# ---- prompt caching ----


def test_cache_split_keeps_the_text_identical():
    for task in QA + EXTRACTION + CODEFIX:
        content = cached_content(task.input)
        assert text_of(content) == task.input, task.id


def test_qa_prefix_is_the_documents_and_breakpoint_is_on_it():
    prefix, rest = split_prefix(QA[0].input)
    assert "Document 2 (product sheet)" in prefix
    assert rest.startswith("\n\nQuestion: ")
    blocks = cached_content(QA[0].input)
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in blocks[1]


def test_qa_prefix_is_identical_across_tasks():
    # Caching only pays if every task shares the same prefix bytes.
    assert len({split_prefix(t.input)[0] for t in QA}) == 1


def test_no_marker_sends_plain_text():
    assert cached_content("just a prompt") == "just a prompt"


def test_prompt_caching_sends_blocks():
    client = CapturingClient(lambda m, p: "30")
    result = PromptCaching(CHEAP).run(QA[0], client)
    assert isinstance(client.requests[0]["messages"][0]["content"], list)
    assert result.passed is True


# ---- context trimming ----


def test_trimming_never_drops_the_needed_document():
    for task in QA:
        label = "returns policy" if task.meta["doc"] == "returns_policy" else "product sheet"
        trimmed = trim_prompt(task.input)
        assert label in trimmed, task.id


def test_trimming_keeps_question_and_instruction():
    trimmed = trim_prompt(QA[0].input)
    assert trimmed.endswith(QA[0].input.rsplit("Question: ", 1)[1])
    assert trimmed.startswith("Answer the question using only the documents below.")
    assert len(trimmed) < len(QA[0].input)


def test_trimming_leaves_other_workloads_alone():
    for task in EXTRACTION + CODEFIX:
        assert trim_prompt(task.input) == task.input


def test_trimming_keeps_all_documents_on_a_tie():
    prompt = (
        "Answer.\n\nDocument 1 (alpha):\n\napples here\n\n"
        "Document 2 (beta):\n\napples there\n\nQuestion: apples?"
    )
    assert trim_prompt(prompt) == prompt


def test_trim_context_sends_the_trimmed_prompt():
    client = CapturingClient(lambda m, p: "30")
    TrimContext(CHEAP).run(QA[0], client)
    assert client.requests[0]["messages"][0]["content"] == trim_prompt(QA[0].input)


# ---- output limits ----


def test_low_effort_sets_output_config():
    client = CapturingClient(lambda m, p: "30")
    LowEffort(CHEAP).run(QA[0], client)
    assert client.requests[0]["options"] == {"output_config": {"effort": "low"}}


# ---- cascade ----


def test_validator_uses_only_the_prompt():
    inv = EXTRACTION[0]
    assert looks_valid(inv, json.dumps(inv.expected)) is True
    assert looks_valid(inv, json.dumps({**inv.expected, "extra": 1})) is False
    assert looks_valid(inv, "not json") is False
    qa = QA[0]
    assert looks_valid(qa, "30") is True
    assert looks_valid(qa, "About 20 minutes.") is False
    assert looks_valid(qa, "15% of the item price") is False
    assert looks_valid(qa, "We do (Oakridge pays)") is False
    fix = CODEFIX[0]
    good = "```python\n" + fix.meta["reference_fix"] + "```"
    assert looks_valid(fix, good) is True
    assert looks_valid(fix, "```python\ndef is_leap_year(y):\n    return False\n```") is False


def test_cascade_stops_at_the_cheap_model_when_valid():
    client = CapturingClient(lambda m, p: "30")
    result = Cascade(CHEAP, STRONG).run(QA[0], client)
    assert [r["model"] for r in client.requests] == [CHEAP]
    assert result.passed is True


def test_cascade_escalates_and_pays_for_both_calls():
    client = CapturingClient(lambda m, p: "It is 30 days." if m == CHEAP else "30")
    result = Cascade(CHEAP, STRONG).run(QA[0], client)
    assert [r["model"] for r in client.requests] == [CHEAP, STRONG]
    assert result.passed is True
    prices = PriceTable.load()
    both = prices.cost(CHEAP, Usage(1_000, 100)) + prices.cost(STRONG, Usage(1_000, 100))
    assert result.cost(prices) == pytest.approx(both)


def test_cascade_escalates_on_api_error():
    class Flaky(CapturingClient):
        def call(self, model, messages, **kw):
            if model == CHEAP:
                raise RuntimeError("overloaded")
            return super().call(model, messages, **kw)

    result = Cascade(CHEAP, STRONG).run(QA[0], Flaky(lambda m, p: "30"))
    assert result.passed is True and result.error is None


# ---- comparison table ----


def _save(store, workload, strategy, results, tasks_hash="h", model=CHEAP):
    return store.save_run(
        workload=workload, strategy=strategy, model=model, tasks_hash=tasks_hash, results=results
    )


def test_comparison_reports_points_and_cost_change(tmp_path):
    prices = PriceTable.load()
    tasks = QA[:4]
    base = run_strategy(tasks, Baseline(CHEAP), CapturingClient(lambda m, p: "nope"), prices)
    good = run_strategy(
        tasks,
        LowEffort(CHEAP),
        CapturingClient(lambda m, p: "30" if "most items" in p else "x"),
        prices,
    )
    with ResultStore(tmp_path / "r.sqlite") as store:
        _save(store, "qa", "baseline", base)
        _save(store, "qa", "low-effort", good)
        _save(store, "qa", "prompt-caching", good[:2])  # a partial (smoke) run
        _save(store, "qa", "trim-context", good, tasks_hash="other")
        table = build_comparison(store, prices)

    assert summarize(good, prices).passed == 1
    assert "| qa | low-effort |" in table and "+25.0 pts" in table
    assert "partial run (2 of 4)" in table
    partial = next(line for line in table.splitlines() if "| prompt-caching |" in line)
    assert "pts" not in partial  # no quality or cost deltas for a partial run
    assert "gate 1 fails" in table
    # Baseline row comes first and has no deltas.
    rows = [line for line in table.splitlines() if line.startswith("| qa |")]
    assert rows[0].startswith("| qa | baseline |")


def test_cli_accepts_every_strategy(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "costlab.cli.ModelClient", lambda *a, **k: CapturingClient(lambda m, p: "{}")
    )
    tasks = tmp_path / "t.jsonl"
    tasks.write_text(
        json.dumps(
            {
                "id": "t1",
                "workload": "extraction",
                "input": "doc",
                "grader": "exact_json",
                "expected": {"a": 1},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "r.sqlite"
    for name in ("baseline", "prompt-caching", "trim-context", "low-effort", "cascade"):
        code = main(
            [
                "run",
                "extraction",
                "--model",
                CHEAP,
                "--strategy",
                name,
                "--tasks",
                str(tasks),
                "--db",
                str(db),
            ]
        )
        assert code == 0, name
    with ResultStore(db) as store:
        assert {r["strategy"] for r in store.latest_runs()} == {
            "baseline",
            "prompt-caching",
            "trim-context",
            "low-effort",
            "cascade",
        }
    assert main(["compare", "--db", str(db)]) == 0


def test_task_dataclass_import_is_used():
    # Keeps the Task import honest for type readers; strategies accept plain Task objects.
    t = Task("x", "qa", "Question?", "yes", "normalized_text")
    assert TrimContext(CHEAP).run(t, CapturingClient(lambda m, p: "yes")).passed is True


def test_combined_sends_cache_breakpoint_and_low_effort():
    from costlab.strategies import Combined

    client = CapturingClient(lambda m, p: "30")
    Combined(CHEAP).run(QA[0], client)
    req = client.requests[0]
    assert req["options"] == {"output_config": {"effort": "low"}}
    assert req["messages"][0]["content"] == cached_content(QA[0].input)
