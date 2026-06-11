"""Optional ORCA graphlet-degree-vector (GDV) signatures — a richer, flag-gated seed fingerprint.

This is **clearly optional** and **not** on the WL path. It is enabled only by
``invariants.gdv_enabled`` and degrades gracefully: if the ``orca`` binary is absent, every entry
point warns and returns ``None`` instead of crashing. (As of this phase no orca binary is installed;
the recommended config default is ``gdv_enabled: false``.)

Like WL, a GDV match is NECESSARY-not-sufficient — it only enriches seeding; the verifier confirms.
"""
from __future__ import annotations

import shutil
import warnings
from typing import Any

from src.io.loader import Dataset


def _orca_path(cfg: dict[str, Any]) -> str:
    """Configured orca binary path (``invariants.orca_path``), defaulting to ``orca`` on PATH."""
    return cfg.get("invariants", {}).get("orca_path", "orca")


def gdv_available(cfg: dict[str, Any]) -> bool:
    """True iff the configured orca binary can be located (on PATH or at an absolute path)."""
    path = _orca_path(cfg)
    return shutil.which(path) is not None


def gdv_signatures(ds: Dataset, cfg: dict[str, Any]) -> dict[str, list[int]] | None:
    """Return per-node GDV signatures, or ``None`` when GDV is disabled or unavailable.

    Sampling fraction is ``invariants.gdv_sample_fraction``. When ``gdv_enabled`` is false this is a
    no-op (returns ``None``). When enabled but the orca binary is missing, it warns and returns
    ``None`` — never raises — so the WL pipeline is unaffected.
    """
    inv = cfg.get("invariants", {})
    if not inv.get("gdv_enabled", False):
        return None
    if not gdv_available(cfg):
        warnings.warn(
            f"invariants.gdv_enabled is true but the orca binary "
            f"({_orca_path(cfg)!r}) was not found; skipping GDV. "
            f"Set invariants.gdv_enabled: false or install ORCA to silence this.",
            RuntimeWarning,
            stacklevel=2,
        )
        return None

    # Binary present: real GDV computation would shell out to orca here on a sampled node set.
    # Deferred until an engine actually consumes GDV seeds; WL is the active filter this phase.
    raise NotImplementedError(
        "ORCA binary found but GDV computation is not wired up yet (deferred; WL is the active filter)."
    )
