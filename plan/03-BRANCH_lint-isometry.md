# Fix: bpmn-io 0.2.1 — bpmnlint isometry on the full corpus

## Objective
Close the isometry gaps found after the 0.2.0 release by an independent Python/Node differential over all 394 vendored `.bpmn` diagrams (recommended config): 343 identical, the rest differing in two real ways. Release **0.2.1** once the full-corpus oracle is byte-identical for `bpmnlint:recommended` and `bpmnlint:all`.

## Findings (supervisor differential, 2026-10-14)
- **F1 — rule-error not reproduced (15 diagrams, rules `global` and `no-bpmndi`).** Upstream reads collections without a fallback where the source has none, e.g. `rules/global.js:64` `definitions.rootElements.filter(...)` and `rules/no-bpmndi.js:67` `rootElements.map(...)`. On definitions without root elements JS throws, and the linter reports `{category: "rule-error", message: "Cannot read properties of undefined (reading 'filter')"}` (resp. `'map'`). The Python rules use `helper.prop_list()` (`node.<name> || []`) at those sites, so no error is raised. Example: `tests/upstream/bpmn-auto-layout/test/fixtures/scenario.empty-definitions.bpmn`.
- **F2 — CLI `--json` writes `"id": null` for elements without id**, where JSON.stringify semantics omit the key (`bpmn_io/cli.py` lint JSON path). The library API keeps `UNDEFINED`, which is correct.
- **F3 — the lint oracle covered only bpmnlint's own diagrams and only `recommended`** (`tests/oracle/test_lint_reports.py`), which is why CI did not catch F1.
- **F4 — Dependabot opens security updates on vendored upstream manifests** (`tests/upstream/bpmnlint/test/integration/bundling`), which must never be edited.

## Scope / Guardrails
- Same method and rules as `plan/done/02-BRANCH_lint.md` (literal port, upstream as the only source, no attribution trailers, local gate before every commit, English text).
- Tests first: the extended oracle test is committed red (as `xfail(strict=True)` with the reason) before the fix, then flipped.

## Branch Scope Boundaries (MANDATORY)
- **Allowed Paths**: `src/bpmn_io/lint/**`, `src/bpmn_io/_js.py`, `src/bpmn_io/cli.py`, `tests/**` (except `tests/upstream/**`), `tests/oracle/run.mjs`, `docs/**`, `README.md`, `CHANGELOG.md`, `plan/03-BRANCH_lint-isometry.md`
- **Forbidden Paths**: `tests/upstream/**`, `src/bpmn_io/resources/**`, `UPSTREAM.toml`, `UPSTREAM.lock`, `LICENSE`, `plan/done/**`, `tmp/**`
- **Conditional Paths**: `pyproject.toml` (version only, BR03-EX1), `.github/dependabot.yml` (BR03-EX2)

## Feedback Loop
- `acknowledge` BR03-EX1: version `0.2.1` in `pyproject.toml`. Rollback: `git checkout`.
- `acknowledge` BR03-EX2: exclude `tests/upstream/**` from Dependabot (`exclude-paths`), keeping `/tests/oracle` as the upstream-moved signal. Rollback: `git checkout`.

## Plan / Todo (lot-based)
- [ ] **Lot 16 — Full-corpus lint oracle (red first)**
  - [ ] `tests/oracle/test_lint_reports.py`: parametrize over every vendored `.bpmn` that both sides parse (same parse outcome asserted otherwise) × configs `bpmnlint:recommended` and `bpmnlint:all`; canonical comparison with JSON.stringify semantics (undefined keys dropped) on both sides; commit with the F1 cases marked `xfail(strict=True)`.
  - [ ] Lot gate.
- [ ] **Lot 17 — JS property-access semantics in rules**
  - [ ] `_js.py`: a strict member read for collections that returns `UNDEFINED` when unset, and JS-style method calls on `UNDEFINED`/`None` raising a `TypeError` whose message is exactly V8's `Cannot read properties of undefined (reading '<name>')` (resp. `null`).
  - [ ] Audit ALL 58 `prop_list()` call sites against the upstream rule source: keep the `|| []` fallback only where upstream has it (`|| []`, `?.`, `get()` on an isMany property); use the strict read elsewhere. Record the audit table in `docs/naming.md` § bpmnlint property access.
  - [ ] Linter reports the raised error as `rule-error` with the same message (already the upstream path); unit tests per affected rule with the empty-definitions diagram.
  - [ ] Flip the Lot 16 xfails; lot gate.
- [ ] **Lot 18 — CLI JSON, Dependabot, release 0.2.1**
  - [ ] CLI `--json` serializes reports with JSON.stringify semantics (omit undefined keys) + test (F2).
  - [ ] `.github/dependabot.yml` excludes `tests/upstream/**` (BR03-EX2) (F4).
  - [ ] CHANGELOG 0.2.1, version bump (BR03-EX1), PR → CI green → merge commit → tag `v0.2.1` → verify PyPI and GitHub release → move this file to `plan/done/`.
