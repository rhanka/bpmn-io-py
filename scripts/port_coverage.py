#!/usr/bin/env python3
"""Measure how much of the upstream JS test-suites is ported to Python.

Every upstream `it('<title>')` (and `it.skip`, reported separately) found under `tests/upstream/`
must be claimed by exactly one Python test carrying the marker::

    @pytest.mark.upstream("bpmn-moddle/spec/xml/read.js", "should import simple process")

The script cross-references both sides and prints a per-file table.

Usage:
  scripts/port_coverage.py            # report
  scripts/port_coverage.py --strict   # exit 1 unless 100 % of upstream cases are claimed (CI gate)
  scripts/port_coverage.py --json     # machine-readable report

stdlib only.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "tests" / "upstream"
PY_TESTS = ROOT / "tests"

# it('title'), it("title"), it(`title`), it.skip(...), it.only(...)
IT_RE = re.compile(
    r"""^\s*it(?P<mod>\.skip|\.only)?\(\s*(?P<q>['"`])(?P<title>.*?)(?P=q)\s*,""", re.MULTILINE
)


def upstream_cases() -> dict[str, dict[str, str]]:
    """Return {relative js file: {title: 'active'|'skip'}}."""
    cases: dict[str, dict[str, str]] = {}
    for js in sorted(UPSTREAM.rglob("*.js")):
        rel = str(js.relative_to(UPSTREAM))
        found: dict[str, str] = {}
        for m in IT_RE.finditer(js.read_text(encoding="utf-8")):
            found[m["title"]] = "skip" if m["mod"] == ".skip" else "active"
        if found:
            cases[rel] = found
    return cases


def _marker_args(node: ast.AST) -> tuple[str, str] | None:
    """Extract ("file", "title") from a `pytest.mark.upstream(...)` decorator node."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "upstream"):
        return None
    if len(node.args) != 2 or not all(isinstance(a, ast.Constant) for a in node.args):
        return None
    file_, title = (a.value for a in node.args)  # type: ignore[attr-defined]
    return str(file_), str(title)


def python_claims() -> dict[tuple[str, str], list[str]]:
    """Return {(js file, title): [python test qualified names]}."""
    claims: dict[tuple[str, str], list[str]] = defaultdict(list)
    for py in sorted(PY_TESTS.rglob("test_*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for deco in node.decorator_list:
                key = _marker_args(deco)
                if key:
                    claims[key].append(f"{py.relative_to(ROOT)}::{node.name}")
    return claims


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    as_json = "--json" in argv
    cases = upstream_cases()
    claims = python_claims()

    report: dict[str, dict[str, object]] = {}
    total = ported = 0
    problems: list[str] = []
    for file_, titles in cases.items():
        active = [t for t, kind in titles.items() if kind == "active"]
        skipped = [t for t, kind in titles.items() if kind == "skip"]
        done = [t for t in active if (file_, t) in claims]
        missing = [t for t in active if (file_, t) not in claims]
        total += len(active)
        ported += len(done)
        report[file_] = {
            "active": len(active),
            "ported": len(done),
            "skipped": len(skipped),
            "missing": missing,
        }
    for (file_, title), names in claims.items():
        if file_ not in cases or title not in cases[file_]:
            problems.append(f"stale claim {file_!r}::{title!r} in {', '.join(names)}")
        elif len(names) > 1:
            problems.append(f"duplicate claim {file_!r}::{title!r} in {', '.join(names)}")

    pct = 100.0 * ported / total if total else 0.0
    if as_json:
        payload = {
            "total": total,
            "ported": ported,
            "percent": pct,
            "files": report,
            "problems": problems,
        }
        print(json.dumps(payload, indent=2))
    else:
        width = max((len(f) for f in report), default=20)
        print(f"{'upstream test file':<{width}}  ported/active  skipped")
        for file_, row in report.items():
            line = (
                f"{file_:<{width}}  {row['ported']:>3}/{row['active']:<3}       {row['skipped']:>3}"
            )
            print(line)
        print(f"\n{ported}/{total} upstream test cases ported ({pct:.1f} %)")
        for p in problems:
            print(f"PROBLEM: {p}")
    if problems:
        return 1
    if strict and ported < total:
        print("strict mode: port is incomplete")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
