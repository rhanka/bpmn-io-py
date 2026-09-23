#!/usr/bin/env python3
"""Measure how much of the upstream JS test-suites is ported to Python.

Every upstream test case found under `tests/upstream/` must be claimed by exactly one Python test
carrying the marker::

    @pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "should import simple process")

Upstream cases come from two sources, merged:

* a static scan of `it(...)`, `it.skip(...)`, `it.only(...)` and the `iit(<arg>)(...)` wrapper in
  every `*.js`, `*.cjs`, `*.mjs`, `*.ts` file;
* `tests/upstream/LEDGER.json` when present ({"<file>": ["<full title>", ...]}), produced by the
  oracle job with a mocha dry-run, which is the only reliable source for *dynamic* titles
  (template literals such as `should layout ${fileName}`).

Without the ledger, dynamic titles of `bpmn-auto-layout/test/LayoutSpec.js` are expanded from the
fixture files (one case per `fixtures/*.bpmn`); any other dynamic title is reported as unresolved.

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
LEDGER = UPSTREAM / "LEDGER.json"
PY_TESTS = ROOT / "tests"
SUFFIXES = (".js", ".cjs", ".mjs", ".ts")

# it('title'), it("title"), it(`title`), it.skip(...), it.only(...), iit(arg)('title', ...)
IT_RE = re.compile(
    r"""^\s*(?:it|iit\([^)]*\))(?P<mod>\.skip|\.only)?\(\s*(?P<q>['"`])(?P<title>.*?)(?P=q)\s*,""",
    re.MULTILINE,
)
DYNAMIC = "${"


def _expand_dynamic(file_: str, title: str) -> list[str] | None:
    """Built-in expansion for the known dynamic titles; None when unresolved.

    Mirrors the upstream loops: `readdirSync(fixtures).filter(.bpmn)` in LayoutSpec.js and
    `FastGlob.globSync('test/fixtures/model/**/*.json')` (paths relative to the moddle repo root)
    in schema.js.
    """
    compact = title.replace(" ", "")
    if file_ == "bpmn-auto-layout/test/LayoutSpec.js" and compact == "shouldlayout${fileName}":
        fixtures = sorted((UPSTREAM / "bpmn-auto-layout" / "test" / "fixtures").glob("*.bpmn"))
        return [f"should layout {f.name}" for f in fixtures]
    if file_ == "moddle/test/spec/schema.js" and compact == "shouldvalidatefixture:${file}":
        repo = UPSTREAM / "moddle"
        models = sorted((repo / "test" / "fixtures" / "model").rglob("*.json"))
        return [f"should validate fixture: {m.relative_to(repo).as_posix()}" for m in models]
    return None


def upstream_cases() -> tuple[dict[str, dict[str, str]], list[str]]:
    """Return ({relative file: {title: 'active'|'skip'}}, [unresolved dynamic titles])."""
    cases: dict[str, dict[str, str]] = {}
    unresolved: list[str] = []
    ledger: dict[str, list[str]] = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    for src in sorted(p for p in UPSTREAM.rglob("*") if p.suffix in SUFFIXES):
        rel = str(src.relative_to(UPSTREAM))
        found: dict[str, str] = {}
        for m in IT_RE.finditer(src.read_text(encoding="utf-8")):
            kind = "skip" if m["mod"] == ".skip" else "active"
            title = m["title"]
            if DYNAMIC not in title:
                found[title] = kind
                continue
            if rel in ledger:
                continue  # the ledger enumerates this file's real titles below
            expanded = _expand_dynamic(rel, title)
            if expanded is None:
                unresolved.append(f"{rel}::{title}")
            else:
                found.update(dict.fromkeys(expanded, kind))
        for title in ledger.get(rel, []):
            found.setdefault(title, "active")
        if found:
            cases[rel] = found
    return cases, unresolved


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
        if UPSTREAM in py.parents:
            continue
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
    cases, unresolved = upstream_cases()
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
    if strict:
        problems.extend(f"unresolved dynamic title {u} (ledger needed)" for u in unresolved)

    pct = 100.0 * ported / total if total else 0.0
    if as_json:
        payload = {
            "total": total,
            "ported": ported,
            "percent": pct,
            "files": report,
            "unresolved_dynamic": unresolved,
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
        for u in unresolved:
            print(f"DYNAMIC (unresolved without ledger): {u}")
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
