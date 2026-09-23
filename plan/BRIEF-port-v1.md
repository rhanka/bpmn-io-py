# Brief — implementing agent for `plan/01-BRANCH_port-v1.md`

You are the implementing agent for this repository (GitHub `rhanka/bpmn-py`), on branch `port-v1`
(already created and checked out). A supervising session reviews your commits and the CI; you do not
need its permission to execute the plan.

## Mission

Execute, lot by lot and in order, `plan/01-BRANCH_port-v1.md`. The design is
`spec/SPEC_EVOL_BPMN_PY.md` (decisions D1–D14); the working rules are in `CONTRIBUTING.md`. Read
those three files completely before writing any code, then start Lot 0.

## What the project is

A literal, systematic transposition to pure Python of the bpmn.io stack: saxen, the used subset of
min-dash, moddle, moddle-xml, bpmn-moddle, bpmn-auto-layout, at the versions pinned in
`UPSTREAM.toml`. The upstream test-suites, helpers, fixtures and snapshots are vendored verbatim under
`tests/upstream/<pkg>/test/` and the upstream sources to transpose under `tests/upstream/<pkg>/lib/`,
both at the pinned commit and sha256-locked (read-only). The pinned JS packages used as a
differential oracle are installed by `cd tests/oracle && npm ci --ignore-scripts`. Priority is
byte-identical behaviour: `to_xml` output and auto-layout snapshots must match upstream byte for
byte, verified through the Node oracle, which is built first (Lot 1) and gates every later lot.

## Hard rules

1. Never edit `tests/upstream/**`, `src/bpmn_py/resources/**`, `UPSTREAM.lock`, `LICENSE`,
   `THIRD_PARTY_NOTICES.md`. `scripts/sync_upstream.py --check` must stay green.
2. Every upstream `it()` is claimed by exactly one Python test via
   `@pytest.mark.upstream("<js file relative to tests/upstream>", "<exact it title>")`; adapted or
   N-A cases are still claimed (a `pytest.skip` with the reason for N-A). Check with
   `uv run python scripts/port_coverage.py`; never leave stale or duplicate claims.
3. Literal port: same file split, same function order and names in snake_case, same warning and
   error texts; each ported module starts with `# Transposed from <repo>@<short-sha> <path> (MIT).`
   Naming rules are decision D3 (write `docs/naming.md` in Lot 0 and follow it).
4. Zero runtime dependency. Reader, writer and matchers must be iterative (upstream tests nest
   50 000 levels).
5. Commit discipline: one logical change per commit, `git add <explicit files>` only, commits under
   about 150 lines, update the checkboxes of `plan/01-BRANCH_port-v1.md` inside the same commit,
   conventional message (`feat:`, `test:`, `docs:`, `chore:`). ABSOLUTELY NO attribution trailers:
   no `Co-Authored-By`, no `Generated with`, no session or agent ids in commit messages.
6. Local gate before every push:
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run python scripts/port_coverage.py`.
   Push to `origin port-v1` at the end of every lot at least; CI must be green
   (`gh run list --branch port-v1`).
7. Conditional paths (`pyproject.toml`, `.github/workflows/**`, `tests/oracle/package*.json`,
   `spec/SPEC_EVOL_BPMN_PY.md`) require an exception `BR01-EXn` declared in the `## Feedback Loop`
   section of the plan before the change (reason, impact, rollback).
8. All repository text in English. Do not ask the supervisor for routine decisions; decide, record
   the rationale in the plan's Feedback Loop, and continue. Stop only for a real blocker, and then
   write it as a `blocked` entry in the Feedback Loop, commit and push.

## Start

Lot 0 first. Work autonomously through Lot 9; Lot 10 contains owner actions and is executed only up
to the owner steps.
