# Feature: bpmn-io 0.2.0 — literal port of bpmn-io `bpmnlint` (L2 semantic rules)

## Objective
Transpose `bpmnlint` 11.15.0 (with its runtime helpers `bpmnlint-utils` 1.1.1 and `@bpmn-io/moddle-utils` 0.3.0) to pure Python with the same literal-port method as `plan/done/01-BRANCH_port-v1.md`, so `bpmn-io` ships moddle + auto-layout + lint as one isometric library, released as **0.2.0** on PyPI (0.1.0 is already published without lint). Design base: `spec/SPEC_EVOL_BPMN_PY.md` D9 (L2 via `bpmnlint`), amended by BR02-EX2.

## Scope / Guardrails
- Literal transposition: same file split, same function order and names (snake_case), same rule messages, rule names, config names (`bpmnlint:recommended`, `bpmnlint:all`, `bpmnlint:correctness`) and report shapes; every ported module starts with `# Transposed from <repo>@<short-sha> <path> (MIT).`
- Upstream sources are ONLY the vendored trees `tests/upstream/{bpmnlint,bpmnlint-utils,moddle-utils}/**` (pinned commit, sha256 in `UPSTREAM.lock`). The workbench clone `tmp/wb-functions` (branch `workbench/functions-20261004`, a non-literal G3 port) is NOT a port source and must not be copied from; it may be read only to anticipate pitfalls.
- Never hand-edit `tests/upstream/**`, `src/bpmn_io/resources/**`, `UPSTREAM.lock`, `LICENSE`.
- Every upstream test case claimed with `@pytest.mark.upstream("<file>", "<title>")` (ported / adapted / N-A with reason); no test dropped silently. RuleTester-generated cases (`rules/<name> > should lint valid|invalid > test case #N`) are keyed by their FULL mocha title from `tests/upstream/LEDGER.json`, because short titles repeat inside one file.
- Zero runtime dependency; iterative traversal (no recursion); JS semantics only through `bpmn_io/_js.py`; naming rules per `docs/naming.md` (D3); sync API per D4.1 (`linter.lint()` returns the report, no promise).
- Rule plugin API kept isometric with upstream (resolver: `resolve_rule(pkg, rule_name)`, `resolve_config(pkg, config_name)`, plugin prefix `bpmnlint-plugin-*`, `extends`, rule flags `off|warn|error|info` and numeric 0..3 (`3 = info`, upstream `lib/linter.js` categoryMap), per-rule config objects): this is the extension point downstream profiles build on.
- Commit discipline: one logical change per commit, selective `git add <files>`, under ~150 lines per commit where possible (a single upstream rule + its test may exceed it), lot checkboxes updated within the commit, NO attribution trailers of any kind (no `Co-Authored-By`, no `Generated with`, no session/agent ids).
- Local gate before every commit: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m mypy && .venv/bin/python -m pytest && .venv/bin/python scripts/port_coverage.py && .venv/bin/python scripts/sync_upstream.py --check`.
- All repository text in English.

## Branch Scope Boundaries (MANDATORY)
- **Allowed Paths (implementation scope)**:
  - `src/bpmn_io/lint/**`, `src/bpmn_io/_bpmnlint_utils.py`, `src/bpmn_io/_moddle_utils.py`
  - `src/bpmn_io/__init__.py`, `src/bpmn_io/cli.py`, `src/bpmn_io/upstream.py`
  - `tests/**` (except `tests/upstream/**` other than the generated `tests/upstream/LEDGER.json`)
  - `scripts/**`, `docs/**`, `README.md`, `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md` (new rows only)
  - `plan/02-BRANCH_lint.md`
- **Forbidden Paths (must not change in this branch)**:
  - `tests/upstream/**` except `LEDGER.json`, `src/bpmn_io/resources/**`, `UPSTREAM.lock` (regenerated only by `scripts/sync_upstream.py`)
  - `LICENSE`, `spec/SPEC_STUDY_BPMN_MODDLE_PY.md`, `plan/done/**`
  - `tmp/**` (workbench clone, not part of this branch)
- **Conditional Paths (allowed only with explicit exception when not already listed in Allowed Paths)**:
  - `UPSTREAM.toml` (BR02-EX1), `spec/SPEC_EVOL_BPMN_PY.md` (BR02-EX2), `pyproject.toml` (BR02-EX3)
  - `.github/workflows/**`, `tests/oracle/package.json`, `tests/oracle/package-lock.json` (BR02-EX4)
- **Exception process**:
  - Declare exception ID `BR02-EXn` in `## Feedback Loop` before touching any conditional/forbidden path, with reason, impact, rollback.

## Feedback Loop
- `acknowledge` BR02-EX1: `UPSTREAM.toml` additions (`bpmnlint` 11.15.0 @ de71146c4a55c7834061c7e5e06c97907d9cdff8, `bpmnlint-utils` 1.1.1 @ 83543fa1261b2098fa90a17ebccdf7c63d75ee64, `moddle-utils` 0.3.0 @ 30e00f7dfc76ad0a0ef9ad40cc28c80e0d5a5349) + `UPSTREAM.lock` regeneration through `scripts/sync_upstream.py` only. Rollback: `git checkout` both + delete the three vendored trees.
- `acknowledge` BR02-EX2: amend EVOL D9 (L2 in scope through `bpmnlint`, released in 0.2.0). Rollback: `git checkout` the spec.
- `acknowledge` BR02-EX3: `pyproject.toml` version `0.2.0`, description/keywords mention bpmnlint, CLI subcommand `lint` needs no new entry point. Rollback: `git checkout`.
- `acknowledge` BR02-EX4: oracle pins `bpmnlint`, `bpmnlint-utils`, `@bpmn-io/moddle-utils` (exact versions) + ledger generation over the bpmnlint suites in CI. Rollback: `git checkout`.
- `attention` BR02-D2: CI `port_coverage.py --strict` is red from Lot 11 until Lot 14 claims the
  bpmnlint suites (904/1100 after Lot 13); every other CI job stays green. Sequencing inherent
  to the lot order; resolves at Lot 14 completion, gate re-checked at Lot 15.
- `acknowledge` BR02-D1: the oracle differential on canonical lint reports needs the built-in
  rules, so the `lint-reports` oracle op lands in Lot 13 and its differential test lands with
  the rules in Lot 14. Rollback: drop the op from `tests/oracle/run.mjs`.
- `acknowledge` BR02-R0: 0.1.0 shipped without lint; this branch releases 0.2.0 on its own (tag `v0.2.0` after merge, Trusted Publishing already configured by the owner).

## Orchestration Mode (AI-selected)
- [x] **Mono-branch + cherry-pick** (default for orthogonal tasks; single final test cycle)
- [ ] **Multi-branch** (only if sub-workstreams require independent CI or long-running validation)
- Rationale: lots are sequential (helpers → core → rules → CLI); branch `port-lint`, draft PR, CI on every push (`port-*`).

## UAT Management (in orchestration context)
- No UI. UAT = owner runs `bpmn-io lint <file>` on a real `.bpmn` after Lot 14.

## Plan / Todo (lot-based)
- [x] **Lot 11 — Pins, vendoring, oracle, ledger**
  - [x] Add the three `[upstream.*]` pins (BR02-EX1) vendoring `lib/`, `rules/`, `config/`, `test/` of bpmnlint, `lib/` + `test/` of bpmnlint-utils, `index.js` + `test/` of moddle-utils; run `scripts/sync_upstream.py`; `src/bpmn_io/upstream.py` + `THIRD_PARTY_NOTICES.md` rows (holders read from each vendored LICENSE).
  - [x] Oracle pins (BR02-EX4) and `tests/oracle/ledger.mjs` extended to the bpmnlint suites; `tests/upstream/LEDGER.json` regenerated with FULL titles for RuleTester cases; `scripts/port_coverage.py` keyed accordingly (static scan stays for the other suites).
  - [x] Lot gate (same checklist as above).
- [x] **Lot 12 — Helpers**
  - [x] `src/bpmn_io/_moddle_utils.py` (from `moddle-utils/index.js`) and `src/bpmn_io/_bpmnlint_utils.py` (from `bpmnlint-utils/lib/**`), with every upstream test claimed and an oracle differential per helper.
  - [x] Lot gate.
- [x] **Lot 13 — Linter core**
  - [x] `src/bpmn_io/lint/` from `bpmnlint/lib/**`: `traverse`, `linter` (`Linter(config_name=..., resolver=...)`, `lint(root, config) -> dict[rule_name, list[report]]`, flags, `extends` resolution, config caching), `resolver` (node-style resolver adapted to Python plugin discovery: built-ins + `entry_points(group="bpmnlint.plugins")`, documented in `docs/naming.md`), `test_rule`, `testers/rule_tester.py` (pytest-driven `verify`), `support/**`.
  - [x] `tests/lint/test_*.py`: claim every case of `test/spec/**` and `test/integration/**`; CLI/bundling/compilation suites claimed N-A with reason (JS packaging) or adapted to `bpmn-io lint`; oracle differential on canonical reports for every bpmnlint test diagram.
  - [x] Lot gate.
- [x] **Lot 14 — Built-in rules, configs, CLI, docs**
  - [x] `src/bpmn_io/lint/rules/*.py` — all 29 rules from `bpmnlint/rules/*.js`; `src/bpmn_io/lint/config/{all,recommended,correctness}.py` from `config/*.js`.
  - [x] `tests/lint/rules/test_*.py`: one claimed case per RuleTester case (full title), byte-exact messages; oracle differential for every rule diagram.
  - [x] `bpmn-io lint <file> [--config NAME] [--json]` with stable exit codes (0 clean, 1 errors) + tests; README (lint section, upstream table), CHANGELOG 0.2.0.
  - [x] Lot gate.
- [ ] **Lot 15 — Release 0.2.0**
  - [x] `port_coverage.py --strict` 100 % over all suites incl. bpmnlint; full gate green; CI green on the PR.
  - [x] Version `0.2.0` (BR02-EX3); EVOL D9 amended (BR02-EX2).
  - [x] Mark the PR ready, merge commit (NO squash, NO rebase), preserve branch, tag `v0.2.0` on `main`, verify the PyPI release and the GitHub release.
  - [ ] Move this file to `plan/done/02-BRANCH_lint.md`.
