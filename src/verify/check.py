"""Independent verifier — the grading oracle (assumptions A9/A10/A15).

This module mirrors FlyWire's grading and is deliberately independent of every engine: it loads via
``src.io`` and otherwise uses **plain dict/set adjacency only**. It imports **no** graph library
(no igraph, no networkx) — that hard rule is enforced by a subprocess test in ``tests/test_verify``.

The candidate ``network.csv`` has 3 columns (dataset names in the header) and N rows of string IDs.
The rows *are* the vertex bijection: the verifier never searches for a mapping, it only checks
edge-consistency under that fixed row alignment, in this order, short-circuiting at the first failure:

  1. structural   — exactly 3 distinct known datasets; N >= 2 rows; 3 non-empty cells per row;
                    no duplicate ID within a column.
  2. existence    — every ID is a node in its dataset.
  3. induced iso  — for every ordered row pair (i, j), edge i->j is present in ALL three induced
                    subgraphs or in NONE; likewise j->i.
  4. weak connect — the shared structure's undirected projection is connected (hand-rolled union-find).

Directed-edge presence is tested as ``(u, v) in ds.edges`` (a ``set`` of compact-int edge tuples):
O(1) lookups with no per-node allocation, so the O(N^2) checks stay cheap even on the 6 M-edge
BANC/FAFB graphs.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.io import load_dataset

_CHECK_NAMES = {
    1: "structural",
    2: "existence",
    3: "induced isomorphism",
    4: "weak connectivity",
}


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckResult:
    index: int            # 1..4
    name: str
    passed: bool
    detail: str           # "" when passed; a precise reason when failed


@dataclass(frozen=True)
class Report:
    ok: bool
    n: int                                  # number of matched neurons (data rows)
    datasets: tuple[str, ...]               # the column / dataset names
    structure: str                          # clique | star | complete_bipartite | general | ""
    checks: tuple[CheckResult, ...]         # one per executed check (later checks omitted on failure)
    failed_check: int | None                # index of the first failing check, else None
    reason: str                             # first failure's detail, else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "n": self.n,
            "datasets": list(self.datasets),
            "structure": self.structure,
            "failed_check": self.failed_check,
            "reason": self.reason,
            "checks": [
                {"index": c.index, "name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }

    def format(self) -> str:
        lines = [
            "Candidate verification",
            f"  datasets : {', '.join(self.datasets) if self.datasets else '(none)'}",
            f"  N (rows) : {self.n}",
        ]
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            dots = "." * max(3, 26 - len(c.name))
            lines.append(f"  [{c.index}] {c.name} {dots} {status}")
            if not c.passed and c.detail:
                lines.append(f"        -> {c.detail}")
        if self.structure:
            lines.append(f"  structure: {self.structure}")
        lines.append(f"RESULT: {'PASS' if self.ok else 'FAIL'}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Edge-presence primitive
# ---------------------------------------------------------------------------

def _edge_set(ds: Any) -> set[tuple[int, int]]:
    """Directed edge set of compact-int tuples (coerce a list to a set if needed)."""
    return ds.edges if isinstance(ds.edges, set) else set(ds.edges)


# ---------------------------------------------------------------------------
# The four checks
# ---------------------------------------------------------------------------

def _check_structural(
    columns: list[str], rows: list[list[str]], datasets: Mapping[str, Any]
) -> CheckResult:
    name = _CHECK_NAMES[1]
    if len(columns) != 3:
        return CheckResult(1, name, False, f"expected 3 columns, got {len(columns)}")
    if len(set(columns)) != 3:
        dup = next(c for i, c in enumerate(columns) if c in columns[:i])
        return CheckResult(1, name, False, f"duplicate dataset column '{dup}'")
    for col in columns:
        if col not in datasets:
            return CheckResult(1, name, False, f"column '{col}' is not a known dataset")
    if len(rows) < 2:
        return CheckResult(
            1, name, False, f"candidate has {len(rows)} rows; need at least 2 (degenerate)"
        )
    for r, row in enumerate(rows):
        if len(row) != 3:
            return CheckResult(1, name, False, f"row {r} has {len(row)} cells (expected 3)")
        for k, cell in enumerate(row):
            if cell == "":
                return CheckResult(1, name, False, f"row {r} column {columns[k]} is empty")
    for k, col in enumerate(columns):
        seen: dict[str, int] = {}
        for r in range(len(rows)):
            cid = rows[r][k]
            if cid in seen:
                return CheckResult(
                    1, name, False,
                    f"duplicate id '{cid}' in column {col} (rows {seen[cid]} and {r})",
                )
            seen[cid] = r
    return CheckResult(1, name, True, "")


def _check_existence(
    columns: list[str], rows: list[list[str]], datasets: Mapping[str, Any]
) -> CheckResult:
    name = _CHECK_NAMES[2]
    n = len(rows)
    for r in range(n):
        for k, col in enumerate(columns):
            cid = rows[r][k]
            if cid not in datasets[col].id_to_int:
                return CheckResult(
                    2, name, False,
                    f"id '{cid}' (row {r}, column {col}) is not a node in {col}",
                )
    return CheckResult(2, name, True, "")


def _check_isomorphism(
    columns: list[str],
    row_ints: list[list[int]],
    esets: list[set[tuple[int, int]]],
) -> CheckResult:
    name = _CHECK_NAMES[3]
    n = len(row_ints[0])
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            present = [(row_ints[k][i], row_ints[k][j]) in esets[k] for k in range(3)]
            if any(present) and not all(present):
                have = [columns[k] for k in range(3) if present[k]]
                lack = [columns[k] for k in range(3) if not present[k]]
                return CheckResult(
                    3, name, False,
                    f"edge row {i} -> row {j} present in {have} but absent in {lack}",
                )
    return CheckResult(3, name, True, "")


def _check_connectivity(
    n: int, ri0: list[int], eset0: set[tuple[int, int]]
) -> CheckResult:
    name = _CHECK_NAMES[4]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if (ri0[i], ri0[j]) in eset0 or (ri0[j], ri0[i]) in eset0:
                union(i, j)

    comps: dict[int, list[int]] = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    if len(comps) == 1:
        return CheckResult(4, name, True, "")
    members = list(comps.values())
    sizes = sorted((len(m) for m in members), reverse=True)
    ex_i, ex_j = members[0][0], members[1][0]
    detail = (
        f"weakly disconnected: {len(comps)} components (sizes {sizes}); "
        f"rows {ex_i} and {ex_j} are in different components"
    )
    return CheckResult(4, name, False, detail)


# ---------------------------------------------------------------------------
# Structure detection (informational; runs once induced isomorphism holds)
# ---------------------------------------------------------------------------

def _detect_structure(n: int, ri0: list[int], eset0: set[tuple[int, int]]) -> str:
    def has(i: int, j: int) -> bool:
        return (ri0[i], ri0[j]) in eset0

    # reciprocal clique: every ordered pair present in both directions
    if all(has(i, j) for i in range(n) for j in range(n) if i != j):
        return "clique"

    adj: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if has(i, j) or has(j, i):
                adj[i].add(j)
                adj[j].add(i)
    deg = [len(adj[i]) for i in range(n)]
    und_edges = sum(deg) // 2

    # star: undirected K_{1, n-1}
    if n >= 3:
        centers = [i for i in range(n) if deg[i] == n - 1]
        leaves = [i for i in range(n) if deg[i] == 1]
        if len(centers) == 1 and len(leaves) == n - 1 and und_edges == n - 1:
            return "star"

    # complete bipartite (proper: both parts >= 2) — requires a connected, 2-colorable, complete biclique
    color = [-1] * n
    color[0] = 0
    q = deque([0])
    seen = 1
    bipartite = True
    while q:
        u = q.popleft()
        for v in adj[u]:
            if color[v] == -1:
                color[v] = color[u] ^ 1
                seen += 1
                q.append(v)
            elif color[v] == color[u]:
                bipartite = False
    if bipartite and seen == n:
        part_a = [i for i in range(n) if color[i] == 0]
        part_b = [i for i in range(n) if color[i] == 1]
        if (
            len(part_a) >= 2
            and len(part_b) >= 2
            and und_edges == len(part_a) * len(part_b)
            and all(b in adj[a] for a in part_a for b in part_b)
        ):
            return "complete_bipartite"

    return "general"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _assemble(
    checks: list[CheckResult], columns: list[str], n: int, structure: str = ""
) -> Report:
    failed = next((c.index for c in checks if not c.passed), None)
    ok = failed is None and len(checks) == 4
    reason = "" if ok else next((c.detail for c in checks if not c.passed), "")
    return Report(
        ok=ok,
        n=n,
        datasets=tuple(columns),
        structure=structure,
        checks=tuple(checks),
        failed_check=failed,
        reason=reason,
    )


def verify_candidate(
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    datasets: Mapping[str, Any],
) -> Report:
    """Run the four checks under the fixed row alignment and return a :class:`Report`.

    ``columns`` is the raw header (validated to be 3 distinct known datasets), ``rows`` the raw
    cells (ragged tolerated; validated), ``datasets`` maps each column name to a loaded ``Dataset``.
    """
    columns = [c.strip() for c in columns]
    rows = [[c.strip() for c in row] for row in rows]
    n = len(rows)
    checks: list[CheckResult] = []

    c1 = _check_structural(columns, rows, datasets)
    checks.append(c1)
    if not c1.passed:
        return _assemble(checks, columns, n)

    c2 = _check_existence(columns, rows, datasets)
    checks.append(c2)
    if not c2.passed:
        return _assemble(checks, columns, n)

    esets = [_edge_set(datasets[columns[k]]) for k in range(3)]
    row_ints = [[datasets[columns[k]].id_to_int[rows[r][k]] for r in range(n)] for k in range(3)]

    c3 = _check_isomorphism(columns, row_ints, esets)
    checks.append(c3)
    if not c3.passed:
        return _assemble(checks, columns, n)

    structure = _detect_structure(n, row_ints[0], esets[0])

    c4 = _check_connectivity(n, row_ints[0], esets[0])
    checks.append(c4)
    return _assemble(checks, columns, n, structure=structure)


def read_candidate(path: Path | str) -> tuple[list[str], list[list[str]]]:
    """Parse a candidate CSV into (header, rows); cells stripped, blank lines dropped."""
    with open(path, newline="") as fh:
        reader = csv.reader(fh)
        non_empty = [
            [c.strip() for c in row]
            for row in reader
            if row and any(c.strip() for c in row)
        ]
    if not non_empty:
        return [], []
    return non_empty[0], non_empty[1:]


def verify_file(path: Path | str, cfg: dict[str, Any] | None = None) -> Report:
    """Read a candidate CSV, resolve its header to loaded datasets, and verify it.

    Header names are resolved against ``cfg['data']['datasets']``; an unknown or malformed header is
    reported cleanly by check 1 without loading the (large) raw graphs.
    """
    if cfg is None:
        from src import config

        cfg = config.get()
    columns, rows = read_candidate(path)
    known = cfg["data"]["datasets"]
    datasets: dict[str, Any] = {}
    if len(columns) == 3 and len(set(columns)) == 3:
        for name in columns:
            if name in known and name not in datasets:
                datasets[name] = load_dataset(name, cfg)
    return verify_candidate(columns, rows, datasets)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.verify.check",
        description="Independent verifier for a candidate network.csv (the grading oracle).",
    )
    parser.add_argument("--candidate", default="network.csv", help="path to candidate CSV")
    parser.add_argument("--config", default=None, help="path to a config.yaml (default: repo config)")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    from src import config

    cfg = config.load(args.config) if args.config else config.get()
    try:
        report = verify_file(args.candidate, cfg=cfg)
    except FileNotFoundError:
        print(f"error: candidate not found: {args.candidate}", file=sys.stderr)
        return 2

    print(json.dumps(report.to_dict(), indent=2) if args.json else report.format())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
