"""Record/replay cache: every real response is saved once and replayed for free."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from costlab.paths import project_path, search_dirs


def default_cache_dir() -> Path:
    """Where new answers are written: the project folder's cache/."""
    return project_path("cache")


class ResponseCache:
    def __init__(self, root: Path | str | None = None, read_also: list[Path] | None = None):
        """Writes go to `root`; reads also look in `read_also` (read-only).

        With no `root`, the cache is the project folder's cache/, and reads fall back to the
        bundled benchmark's recorded answers, so a fresh install replays them without a key.
        """
        if root is None:
            self.root = default_cache_dir()
            fallbacks = [d / "cache" for d in search_dirs()] if read_also is None else read_also
        else:
            self.root = Path(root)
            fallbacks = read_also or []
        here = self.root.resolve()
        self.read_also = [p for p in fallbacks if p.resolve() != here]

    @staticmethod
    def key(request: dict[str, Any]) -> str:
        # sort_keys makes the key independent of dict order, so the same
        # request always maps to the same file.
        canonical = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _path(root: Path, key: str) -> Path:
        return root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        for root in (self.root, *self.read_also):
            path = self._path(root, key)
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return None

    def put(self, key: str, entry: dict[str, Any]) -> None:
        path = self._path(self.root, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
