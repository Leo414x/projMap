from __future__ import annotations

import json
from pathlib import Path


class FileHashCache:
    """JSON-backed cache mapping file path -> content hash."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.path = Path(cache_dir) / "file_hashes.json"
        self._data: dict[str, str] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text())

    def get(self, file_path: str) -> str | None:
        return self._data.get(file_path)

    def set(self, file_path: str, content_hash: str) -> None:
        self._data[file_path] = content_hash

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))

    def as_dict(self) -> dict[str, str]:
        return dict(self._data)
