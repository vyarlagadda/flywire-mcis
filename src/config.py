"""Project-wide configuration loader and helpers."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).parent.parent
_DEFAULT_CONFIG = _ROOT / "config.yaml"

_cfg: dict[str, Any] | None = None
_seed_override: int | None = None
_active_config_path: Path | None = None


def load(path: Path | str | None = None) -> dict[str, Any]:
    """Load config from *path* and cache it.

    Priority (highest first):
      1. An explicit *path* argument passed to this function.
      2. The ``FLYWIRE_CONFIG`` environment variable.
      3. The repo-root ``config.yaml`` default.
    """
    global _cfg, _active_config_path
    if path is not None:
        p = Path(path)
    elif (env_val := os.environ.get("FLYWIRE_CONFIG")):
        p = Path(env_val)
    else:
        p = _DEFAULT_CONFIG
    with p.open() as fh:
        _cfg = yaml.safe_load(fh)
    _active_config_path = p
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
    """Copy the active config into *result_dir* as config.snapshot.yaml.

    Copies whichever config file was last loaded by :func:`load`, falling back
    to ``_DEFAULT_CONFIG`` if ``load`` has not been called yet.
    """
    dest = Path(result_dir) / "config.snapshot.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = _active_config_path if _active_config_path is not None else _DEFAULT_CONFIG
    shutil.copy2(source, dest)
    return dest
