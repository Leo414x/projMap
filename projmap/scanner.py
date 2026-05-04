from __future__ import annotations

import fnmatch
import os
import subprocess
from datetime import datetime
from pathlib import Path

from projmap.config import ProjmapConfig
from projmap.schemas import FileRecord, file_hash


def _should_ignore(path: Path, cfg: ProjmapConfig) -> bool:
    parts = path.parts
    for part in parts:
        if part in cfg.ignore_paths:
            return True
        # Also match glob patterns like *.egg-info
        for pattern in cfg.ignore_paths:
            if "*" in pattern and fnmatch.fnmatch(part, pattern):
                return True
    name = path.name
    for pattern in cfg.ignore_globs:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _is_candidate(path: Path, cfg: ProjmapConfig) -> bool:
    name = path.name
    if name in cfg.include_filenames:
        return True
    suffix = path.suffix.lower()
    if suffix in cfg.include_extensions:
        return True
    return False


def _get_git_log(root: str, limit: int) -> tuple[str, str] | None:
    try:
        result = subprocess.run(
            ["git", "log", f"-n{limit}", "--date=iso",
             "--pretty=format:%h | %ad | %s"],
            capture_output=True, text=True, cwd=root, timeout=10,
        )
        if result.returncode != 0:
            return None
        content = result.stdout.strip()
        if not content:
            return None
        return ("__git_log__", content)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def scan_files(
    cfg: ProjmapConfig,
    known_hashes: dict[str, str] | None = None,
) -> list[FileRecord]:
    root = Path(cfg.root).resolve()
    known_hashes = known_hashes or {}
    records: list[FileRecord] = []

    # Walk filesystem
    for dirpath, dirnames, filenames in os.walk(root):
        dir_path = Path(dirpath)
        # Prune ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in cfg.ignore_paths and not any(
                fnmatch.fnmatch(d, p) for p in cfg.ignore_globs
            )
        ]

        for fname in filenames:
            full = dir_path / fname
            rel = str(full.relative_to(root))

            if _should_ignore(Path(rel), cfg):
                continue
            if not _is_candidate(full, cfg):
                continue

            try:
                content = full.read_text(errors="replace")
            except (OSError, PermissionError):
                continue

            stat = full.stat()
            chash = file_hash(content)
            old_hash = known_hashes.get(rel)
            if old_hash is None:
                status = "new"
            elif old_hash == chash:
                status = "unchanged"
            else:
                status = "changed"

            ext = full.suffix.lower() if full.suffix else ""
            file_type = ext.lstrip(".") if ext else "unknown"

            records.append(FileRecord(
                path=rel,
                file_type=file_type,
                content=content,
                content_hash=chash,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                status=status,
                is_virtual=False,
            ))

    # Virtual git log file
    if cfg.include_git_log:
        git = _get_git_log(cfg.root, cfg.git_log_limit)
        if git:
            name, content = git
            chash = file_hash(content)
            old_hash = known_hashes.get(name)
            if old_hash is None:
                status = "new"
            elif old_hash == chash:
                status = "unchanged"
            else:
                status = "changed"
            records.append(FileRecord(
                path=name,
                file_type="git_log",
                content=content,
                content_hash=chash,
                size_bytes=len(content.encode()),
                modified_at=datetime.now(),
                status=status,
                is_virtual=True,
            ))

    return records
