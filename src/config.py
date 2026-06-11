"""Project-wide configuration loader and helpers."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).parent.parent
_DEFAULT_CONFIG = _ROOT / "config.yaml"

_cfg: dict[str, Any] | None = None
_seed_override: int | None = None


def load(path: Path | str | None = None) -> dict[str, Any]:
    """Load config from *path* (defaults to repo-root config.yaml) and cache it."""
    global _cfg
    p = Path(path) if path else _DEFAULT_CONFIG
    with p.open() as fh:
        _cfg = yaml.safe_load(fh)
    return _cfg


def get() -> dict[str, Any]:
    """Return the cached config, loading defaults if not yet loaded."""
    if _cfg is None:
        load()
    return _cfg  # type: ignore[return-value]


def seed() -> int:
    """Return the active RNG seed (override > config)."""
    if _seed_override is not None:
        return _seed_override
    return int(get()["seed"])


def set_seed(value: int) -> None:
    """Override the RNG seed at runtime without touching config.yaml."""
    global _seed_override
    _seed_override = value


def snapshot(result_dir: Path | str) -> Path:
    """Copy the active config.yaml into *result_dir* as config.snapshot.yaml."""
    dest = Path(result_dir) / "config.snapshot.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_DEFAULT_CONFIG, dest)
    return dest
