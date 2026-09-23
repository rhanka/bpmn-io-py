# Feature: bpmn-io lint — literal port of bpmn-io `bpmnlint` (L2 semantic rules)

## Objective
Transpose `bpmnlint` to pure Python with the same literal-port method as `plan/01-BRANCH_port-v1.md`,
so `bpmn-io` ships moddle + auto-layout + lint in one 0.1.0 publication. Design base:
`spec/SPEC_EVOL_BPMN_PY.md` D9 (L2 via `bpmnlint`, 29 built-in rules evaluated on the
`bpmn-moddle` model); this file amends D9's scope at execution time (BR02-EX2).

## Ordering
Execute AFTER `01-BRANCH_port-v1.md` Lots 0–9 are complete (lint needs the `bpmn_moddle` model),
BEFORE the 01 Lot 10 release steps (version bump, merge, tag). Same branch `port-v1`.

## Scope / Guardrails
- Literal transposition: same file split, same function order and names (snake_case), same rule
  messages and codes; every ported module starts with
  `# Transposed from <repo>@<short-sha> <path> (MIT).`
- Upstream sources are the vendored trees `tests/upstream/bpmnlint/lib/**` and
  `tests/upstream/bpmnlint/test/**` (pinned commit, sha256 in `UPSTREAM.lock`); never read a port
  source from anywhere else; never hand-edit `tests/upstream/**`, `src/bpmn_io/resources/**`,
  `UPSTREAM.lock`, `LICENSE`, `THIRD_PARTY_NOTICES.md`.
- Every upstream `it()` claimed with `@pytest.mark.upstream("<file>", "<title>")`
  (ported / adapted / N-A with reason); no test dropped silently.
- Zero runtime dependency; iterative traversal (no recursion); JS semantics only through
  `bpmn_io/_js.py`; naming rules per `docs/naming.md` (D3).
- Commit discipline: one logical change per commit, selective `git add <files>`, under ~150 lines
  per commit, lot checkboxes updated within the commit, NO attribution trailers of any kind.
- Local gate before every commit: `.venv/bin/ruff check . && .venv/bin/ruff format --check . &&
  .venv/bin/python -m mypy && .venv/bin/python -m pytest &&
  .venv/bin/python scripts/port_coverage.py && .venv/bin/python scripts/sync_upstream.py --check`.
- All repository text in English.

## Feedback Loop
- `acknowledge` BR02-EX1: `UPSTREAM.toml` addition + `UPSTREAM.lock` regeneration through
  `scripts/sync_upstream.py` only. Reason: new upstream package. Impact: added pin + vendored
  trees. Rollback: `git checkout` both + delete `tests/upstream/bpmnlint`.
- `acknowledge` BR02-EX2: amend EVOL D9 (L2 in scope through `bpmnlint`). Reason: owner scope
  decision. Impact: spec text. Rollback: `git checkout` the spec.
- `acknowledge` BR02-EX3: `pyproject.toml` CLI entry for `bpmn-io lint` (+ workflows only if the
  release shape changes). Reason: D10 extension. Impact: entry point. Rollback: `git checkout`.

## Plan / Todo (lot-based)
- [ ] **Lot 11 — bpmnlint upstream pin & ledger**
  - [ ] Resolve the pin: latest stable `bpmnlint` at execution time (`npm view bpmnlint version`,
    repo `bpmn-io/bpmnlint`, tag + commit); add `[upstream.bpmnlint]` to `UPSTREAM.toml`
    (npm + github vendor entries for `lib/` and `test/`); run `scripts/sync_upstream.py`
    (BR02-EX1); record version in `src/bpmn_io/upstream.py` + `THIRD_PARTY_NOTICES.md` row
    (header/table only, same rename pattern as BR01-EX8).
  - [ ] Regenerate `tests/upstream/LEDGER.json` including the bpmnlint suites (oracle job covers it).
  - [ ] Lot gate (same checklist as above).
- [ ] **Lot 12 — linter core**
  - [ ] `src/bpmn_io/lint/` from `tests/upstream/bpmnlint/lib/**`: config load/extends, resolver,
    rule registry, `Linter.lint(element | xml) -> LintReport` (sync mapping per D4.1), rule
    context helpers; message texts and codes identical.
  - [ ] `tests/lint/test_*.py`: claim every case of the core suites
    (`test/spec/*.js` minus `rules/`); oracle differential on canonical reports.
  - [ ] Lot gate (same checklist as above).
- [ ] **Lot 13 — built-in rules, CLI, docs**
  - [ ] Port all built-in rules (`lib/rules/*`, 29 per EVOL) with their tests
    (`test/spec/rules/*`), one claimed case per rule test; byte-exact messages verified
    through the oracle.
  - [ ] `bpmn-io lint <file> [--json]` (BR02-EX3) + tests; README API section; CHANGELOG entry.
  - [ ] UAT checkpoint: owner runs `bpmn-io lint` on a real `.bpmn`.
  - [ ] Lot gate (same checklist as above).
- [ ] **Lot 14 — joint release with 01 Lot 10**
  - [ ] `port_coverage.py --strict` 100 % over all suites incl. bpmnlint; full gate green;
    version `0.1.0`; owner actions (PyPI trusted publisher, tag `v0.1.0`, merge) unchanged.
