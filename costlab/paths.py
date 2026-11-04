"""Where costlab finds its files, so it works from a source checkout and from `pip install`.

Lookups go, in order:
1. the project folder: COSTLAB_HOME, or the current folder (your own tasks, cache, results);
2. the bundled benchmark shipped inside the package (`costlab/_bundle`, filled at build time by
   `scripts/build_bundle.py`): prices, the three workloads, every recorded answer, the run list;
3. the source checkout the package sits in (an editable install run from another folder).

Writes (new cache entries, the results database, reports) always go to the project folder.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
BUNDLE = PACKAGE / "_bundle"
CHECKOUT = PACKAGE.parent


def project_dir() -> Path:
    return Path(os.environ.get("COSTLAB_HOME") or Path.cwd())


def search_dirs() -> list[Path]:
    """Read locations, most specific first, without duplicates."""
    out: list[Path] = []
    for d in (project_dir(), BUNDLE, CHECKOUT):
        d = d.resolve()
        if d not in out:
            out.append(d)
    return out


def find(relative: str) -> Path | None:
    """The first existing `relative` path in the read locations, or None."""
    for base in search_dirs():
        path = base / relative
        if path.exists():
            return path
    return None


def project_path(relative: str) -> Path:
    """Where to write `relative`: always the project folder."""
    return project_dir() / relative
