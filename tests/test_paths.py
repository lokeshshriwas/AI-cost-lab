"""Where costlab looks for files: project folder first, then the bundled benchmark."""

import json
import subprocess
import sys

import pytest

import costlab.paths as paths
from costlab import PriceTable, ResponseCache
from costlab.cli import main


@pytest.fixture
def layout(tmp_path, monkeypatch):
    """A project folder, a fake bundle and a fake checkout, so no real files are involved."""
    project, bundle, checkout = (tmp_path / n for n in ("project", "bundle", "checkout"))
    for d in (project, bundle, checkout):
        d.mkdir()
    monkeypatch.setenv("COSTLAB_HOME", str(project))
    monkeypatch.setattr(paths, "BUNDLE", bundle)
    monkeypatch.setattr(paths, "CHECKOUT", checkout)
    return project, bundle, checkout


def write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_project_folder_wins_then_bundle_then_checkout(layout):
    project, bundle, checkout = layout
    write(checkout / "a.txt")
    assert paths.find("a.txt") == (checkout / "a.txt").resolve()
    write(bundle / "a.txt")
    assert paths.find("a.txt") == (bundle / "a.txt").resolve()
    write(project / "a.txt")
    assert paths.find("a.txt") == (project / "a.txt").resolve()
    assert paths.find("missing.txt") is None


def test_writes_always_go_to_the_project_folder(layout):
    project, _, _ = layout
    assert paths.project_path("results/results.sqlite") == project / "results/results.sqlite"


def test_cache_reads_the_bundle_but_writes_the_project(layout):
    project, bundle, _ = layout
    key = ResponseCache.key({"q": 1})
    write(bundle / "cache" / key[:2] / f"{key}.json", json.dumps({"text": "bundled"}))
    cache = ResponseCache()
    assert cache.root == project / "cache"
    assert cache.get(key) == {"text": "bundled"}
    cache.put(key, {"text": "mine"})
    assert cache.get(key) == {"text": "mine"}  # the project's own answer wins
    assert json.loads((bundle / "cache" / key[:2] / f"{key}.json").read_text()) == {
        "text": "bundled"
    }


def test_explicit_cache_root_has_no_fallback(layout, tmp_path):
    _, bundle, _ = layout
    key = ResponseCache.key({"q": 1})
    write(bundle / "cache" / key[:2] / f"{key}.json", "{}")
    assert ResponseCache(tmp_path / "own").get(key) is None


def test_project_prices_override_the_bundled_ones(layout):
    project, bundle, _ = layout
    yaml = "models:\n  m:\n    input: {x}\n    output: 0\n    cache_write: 0\n    cache_read: 0\n"
    write(bundle / "prices.yaml", yaml.format(x=1.0))
    assert PriceTable.load()._models["m"]["input"] == 1.0
    write(project / "prices.yaml", yaml.format(x=2.0))
    assert PriceTable.load()._models["m"]["input"] == 2.0


def test_missing_prices_is_a_clear_error(layout):
    with pytest.raises(FileNotFoundError, match="prices.yaml"):
        PriceTable.load()


def test_run_with_unknown_workload_says_how_to_fix_it(layout, capsys):
    assert main(["run", "nope", "--model", "claude-haiku-5-5"]) == 2
    assert "--tasks" in capsys.readouterr().err


# ---- the build script ----


def test_build_bundle_copies_exactly_what_rebuild_needs(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "prices.yaml", "models: {}\n")
    write(repo / "workloads" / "qa" / "tasks.jsonl", "{}\n")
    write(repo / "workloads" / "qa" / "docs" / "notes.md")  # not needed: left out
    write(repo / "cache" / "ab" / "abc.json", "{}")
    write(repo / "results" / "runs.json", "[]")
    write(repo / "results" / "results.sqlite")  # derived: left out
    sys.path.insert(0, str(paths.CHECKOUT / "scripts"))
    try:
        from build_bundle import build
    finally:
        sys.path.pop(0)
    bundle = tmp_path / "bundle"
    counts = build(repo, bundle)
    assert counts == {"prices": 1, "workloads": 1, "cache": 1, "manifest": 1}
    shipped = sorted(p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file())
    assert shipped == [
        "cache/ab/abc.json",
        "prices.yaml",
        "results/runs.json",
        "workloads/qa/tasks.jsonl",
    ]


def test_package_data_globs_match_the_bundle_layout():
    # The globs in pyproject.toml must cover every file build_bundle writes.
    import fnmatch
    import tomllib

    globs = tomllib.loads((paths.CHECKOUT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "setuptools"
    ]["package-data"]["costlab"]
    files = [
        "_bundle/prices.yaml",
        "_bundle/results/runs.json",
        "_bundle/cache/ab/abc.json",
        "_bundle/workloads/qa/tasks.jsonl",
    ]
    for f in files:
        assert any(fnmatch.fnmatchcase(f, g) and f.count("/") == g.count("/") for g in globs), f


def test_cli_entry_point_is_declared():
    import tomllib

    scripts = tomllib.loads((paths.CHECKOUT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["scripts"]
    assert scripts == {"costlab": "costlab.cli:main"}
    out = subprocess.run(
        [sys.executable, "-m", "costlab", "--help"], capture_output=True, text=True, check=True
    )
    assert "rebuild" in out.stdout
