from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

DEFAULT_IGNORE_PATHS = [
    ".git",
    ".projmap",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "data",
    "__pycache__",
    ".pytest_cache",
    "*.egg-info",
]

DEFAULT_IGNORE_GLOBS = [
    "*.pyc",
    "*.parquet",
    "*.csv",
    "*.duckdb",
    "*.db",
    "*.sqlite",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.pdf",
]

DEFAULT_INCLUDE_EXTENSIONS = [".md", ".txt"]
DEFAULT_INCLUDE_FILENAMES = ["TODO", "TODO.md", "CLAUDE.md", "README.md"]


@dataclass
class ProjmapConfig:
    project_name: str = "auto"
    root: str = "."
    include_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE_EXTENSIONS))
    include_filenames: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE_FILENAMES))
    include_git_log: bool = True
    git_log_limit: int = 200
    ignore_paths: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_PATHS))
    ignore_globs: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_GLOBS))
    max_chars: int = 12000
    overlap_chars: int = 800
    extraction_mode: str = "external"
    strict_evidence: bool = True
    prompt_version: str = "v1"
    prompt_versions: dict[str, str] = field(default_factory=lambda: {
        "extraction": "v1",
        "relation_discovery": "v1",
        "enrichment": "v1",
        "enrichment_query": "v1",
        "brief_section": "v1",
        "brief_status": "v1",
    })
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    api_key_env: str = "ANTHROPIC_API_KEY"
    temperature: float = 0.0
    database_path: str = ".projmap/projmap.duckdb"
    cache_dir: str = ".projmap/cache"

    @property
    def projmap_dir(self) -> Path:
        return Path(self.root) / ".projmap"

    @property
    def config_path(self) -> Path:
        return self.projmap_dir / "config.toml"

    @property
    def db_path(self) -> Path:
        return Path(self.root) / self.database_path


def _to_toml_dict(cfg: ProjmapConfig) -> dict:
    return {
        "project": {
            "name": cfg.project_name,
            "root": cfg.root,
        },
        "scan": {
            "include_extensions": cfg.include_extensions,
            "include_filenames": cfg.include_filenames,
            "include_git_log": cfg.include_git_log,
            "git_log_limit": cfg.git_log_limit,
            "ignore_paths": cfg.ignore_paths,
            "ignore_globs": cfg.ignore_globs,
        },
        "chunking": {
            "max_chars": cfg.max_chars,
            "overlap_chars": cfg.overlap_chars,
        },
        "extraction": {
            "mode": cfg.extraction_mode,
            "strict_evidence": cfg.strict_evidence,
            "prompt_version": cfg.prompt_version,
        },
        "prompts": cfg.prompt_versions,
        "llm": {
            "provider": cfg.llm_provider,
            "model": cfg.llm_model,
            "api_key_env": cfg.api_key_env,
            "temperature": cfg.temperature,
        },
        "storage": {
            "database_path": cfg.database_path,
            "cache_dir": cfg.cache_dir,
        },
    }


def default_config(root: str = ".") -> ProjmapConfig:
    cfg = ProjmapConfig(root=root)
    if cfg.project_name == "auto":
        cfg.project_name = Path(root).resolve().name
    return cfg


def write_config(cfg: ProjmapConfig) -> Path:
    d = _to_toml_dict(cfg)
    cfg.projmap_dir.mkdir(parents=True, exist_ok=True)
    (cfg.projmap_dir / "cache").mkdir(parents=True, exist_ok=True)
    (cfg.projmap_dir / "logs").mkdir(parents=True, exist_ok=True)
    cfg.config_path.write_text(tomli_w.dumps(d))
    return cfg.config_path


def load_config(root: str = ".") -> ProjmapConfig:
    config_path = Path(root) / ".projmap" / "config.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"No .projmap/config.toml found. Run `projmap init` first.")
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    project = data.get("project", {})
    scan = data.get("scan", {})
    chunking = data.get("chunking", {})
    extraction = data.get("extraction", {})
    llm = data.get("llm", {})
    storage = data.get("storage", {})
    prompts = data.get("prompts", {})

    # Backward compat: if [prompts] missing but [extraction] has prompt_version
    default_pv = {
        "extraction": "v1",
        "relation_discovery": "v1",
        "enrichment": "v1",
        "enrichment_query": "v1",
        "brief_section": "v1",
        "brief_status": "v1",
    }
    if not prompts and extraction.get("prompt_version"):
        default_pv["extraction"] = extraction["prompt_version"]
    prompt_versions = {**default_pv, **prompts}
    return ProjmapConfig(
        project_name=project.get("name", Path(root).resolve().name),
        root=project.get("root", root),
        include_extensions=scan.get("include_extensions", DEFAULT_INCLUDE_EXTENSIONS),
        include_filenames=scan.get("include_filenames", DEFAULT_INCLUDE_FILENAMES),
        include_git_log=scan.get("include_git_log", True),
        git_log_limit=scan.get("git_log_limit", 200),
        ignore_paths=scan.get("ignore_paths", DEFAULT_IGNORE_PATHS),
        ignore_globs=scan.get("ignore_globs", DEFAULT_IGNORE_GLOBS),
        max_chars=chunking.get("max_chars", 12000),
        overlap_chars=chunking.get("overlap_chars", 800),
        extraction_mode=extraction.get("mode", "external"),
        strict_evidence=extraction.get("strict_evidence", True),
        prompt_version=extraction.get("prompt_version", "v1"),
        llm_provider=llm.get("provider", "anthropic"),
        llm_model=llm.get("model", "claude-sonnet-4-20250514"),
        api_key_env=llm.get("api_key_env", "ANTHROPIC_API_KEY"),
        temperature=llm.get("temperature", 0.0),
        database_path=storage.get("database_path", ".projmap/projmap.duckdb"),
        cache_dir=storage.get("cache_dir", ".projmap/cache"),
        prompt_versions=prompt_versions,
    )


def init_projmap(root: str = ".", strict_evidence: bool = True) -> Path:
    cfg = default_config(root)
    cfg.strict_evidence = strict_evidence
    if cfg.include_git_log and not (Path(root) / ".git").exists():
        cfg.include_git_log = False
    write_config(cfg)
    return cfg.projmap_dir
