# Feature: bpmn-py v1 — literal port of the bpmn.io stack (moddle → bpmn-moddle → auto-layout)

## Objective
Transpose saxen, the used min-dash subset, moddle, moddle-xml, bpmn-moddle and bpmn-auto-layout to pure Python, one upstream file at a time, with 100 % of the upstream test-suites claimed and byte-identical XML output (`to_xml` and layout snapshots) verified against the pinned JS packages through the Node oracle. Design: `spec/SPEC_EVOL_BPMN_PY.md` (D1–D14).

## Scope / Guardrails
- Literal transposition: same file split, same function order and names (snake_case), same warnings and error texts; every ported module starts with `# Transposed from <repo>@<short-sha> <path> (MIT).`
- Vendored upstream trees (`tests/upstream/**`, `src/bpmn_py/resources/**`) are never edited by hand; `scripts/sync_upstream.py --check` must stay green.
- Every upstream `it()` is claimed with `@pytest.mark.upstream("<file>", "<title>")` (ported / adapted / N-A with reason); no test is dropped silently.
- Zero runtime dependency; `lxml` only under the `[xsd]` extra and the `test` group; `jsonschema` only in the `test` group.
- Iterative (non-recursive) reader, writer and matchers; JS semantics only through `bpmn_py/_js.py`.
- Commit discipline: one logical change per commit, selective `git add <files>`, under ~150 lines per commit, lot checkboxes updated within the commit, NO attribution trailers of any kind (no `Co-Authored-By`, no `Generated with`, no session ids).
- Local gate before every push: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run python scripts/port_coverage.py`.
- All repository text in English.

## Branch Scope Boundaries (MANDATORY)
- **Allowed Paths (implementation scope)**:
  - `src/bpmn_py/**` (except `src/bpmn_py/resources/**`)
  - `tests/**` (except `tests/upstream/**`)
  - `scripts/**`
  - `docs/**`
  - `README.md`, `CHANGELOG.md`
  - `plan/01-BRANCH_port-v1.md`
- **Forbidden Paths (must not change in this branch)**:
  - `tests/upstream/**`, `src/bpmn_py/resources/**`, `UPSTREAM.lock` (regenerated only by `scripts/sync_upstream.py`)
  - `LICENSE`, `THIRD_PARTY_NOTICES.md`
  - `spec/SPEC_STUDY_BPMN_MODDLE_PY.md`
  - `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`
- **Conditional Paths (allowed only with explicit exception when not already listed in Allowed Paths)**:
  - `pyproject.toml` (dependency groups, markers, tool config only)
  - `.github/workflows/**`, `.github/dependabot.yml`
  - `UPSTREAM.toml` (a version bump is a new branch, not this one)
  - `tests/oracle/package.json`, `tests/oracle/package-lock.json`
  - `spec/SPEC_EVOL_BPMN_PY.md` (docs consolidation lot only)
- **Exception process**:
  - Declare exception ID `BR01-EXn` in `## Feedback Loop` before touching any conditional/forbidden path.
  - Include reason, impact, and rollback strategy.

## Feedback Loop
Actions with the following status should be included around tasks only if really required:
- subagent or agent requires support or informs: `blocked` / `deferred` / `cancelled` / `attention`
- conductor agent or human brings response: `clarification` / `acknowledge` / `refuse`
- `attention` BR01-D12: the PyPI distribution name is still open (`bpmn-py` and `bpmn` are registered by others); it only affects Lot 10.

## Orchestration Mode (AI-selected)
- [x] **Mono-branch + cherry-pick** (default for orthogonal tasks; single final test cycle)
- [ ] **Multi-branch** (only if sub-workstreams require independent CI or long-running validation)
- Rationale: the lots are strictly sequential (each layer depends on the previous one); a single branch `port-v1` with small commits and CI on every push is enough.

## UAT Management (in orchestration context)
- No UI. UAT = the owner runs the README quick-start against a real `.bpmn` (Camunda Modeler export) after Lot 8, and the CLI after Lot 9.
- UAT checkpoints listed as checkboxes inside the relevant lots.

## Plan / Todo (lot-based)
- [ ] **Lot 0 — Baseline & port protocol**
  - [ ] Read `spec/SPEC_EVOL_BPMN_PY.md`, `CONTRIBUTING.md`, `UPSTREAM.toml`; run the local gate once (green baseline).
  - [ ] Write `docs/naming.md`: the JS → Python naming table of D3 (camelCase → snake_case, moddle property names unchanged, `$type` → `type_`, `$attrs` → `attrs_`, `$parent` → `parent_`, `$descriptor` → `descriptor_`, `$model` → `model_`, `$instanceOf` → `instance_of`, keyword properties via `get`/`set` only).
  - [ ] `src/bpmn_py/_js.py` + `tests/test_js.py`: truthiness, `undefined`/`null` sentinel, `math_round` (half-up), `number_to_string` (JS `Number#toString`), `parse_int`/`parse_float`, ordered set, `json_stringify` semantics.
  - [ ] `tests/conftest.py`: register the `upstream` marker helper, `fixtures(pkg)` path helper, `read_fixture(pkg, path)`.
  - [ ] `tests/_matchers.py`: transposed `expect.js` / `matchers.js` (`json_equal` excluding `$parent`/`$model`/`$descriptor`, insertion order kept, iterative).
  - [ ] Lot gate:
    - [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy`
    - [ ] `uv run pytest`
    - [ ] `uv run python scripts/port_coverage.py` runs clean (no stale/duplicate claims)

- [ ] **Lot 1 — min-dash subset**
  - [ ] Inventory every min-dash import in the six upstream `lib/` trees (npm dist bundles in `tests/oracle/node_modules/*/dist`) → list in `docs/naming.md` § min-dash.
  - [ ] `src/bpmn_py/_min_dash.py`: transpose exactly those helpers (array/collection/object/fn/lang), same semantics on dict/list, insertion order kept.
  - [ ] `tests/min_dash/test_*.py`: claim the upstream `tests/upstream/min-dash/*.spec.js` cases covering the transposed helpers; the rest claimed N-A ("helper not used by the ported libraries").
  - [ ] Lot gate (same checklist as Lot 0)

- [ ] **Lot 2 — saxen (lenient SAX parser)**
  - [ ] `src/bpmn_py/saxen/parser.py`: `Parser` with `on(...)` handlers, `ns()` namespace mode, `parse()`; entity decoding (`decode.js`), attribute parsing leniency and warning texts, position (line/column, 0-based as upstream), error texts, `proxy`/`ns` modes, stop/skip control.
  - [ ] Security: no DTD processing, no external entities, only built-in and numeric character references; explicit tests (XXE payload, entity amplification, deep nesting GHSA-x3vc-q6mj-47vp).
  - [ ] `tests/saxen/test_parser.py`, `test_elements.py`, `test_decode.py`, `test_errors.py`, `test_modes.py`, `test_stream.py`: claim every case of `tests/upstream/saxen/*.js`; `test/perf` cases claimed adapted (timeout per CI runner) or N-A with reason.
  - [ ] Lot gate (same checklist as Lot 0)

- [ ] **Lot 3 — moddle (meta-model runtime)**
  - [ ] `src/bpmn_py/moddle/ns.py`, `types.py`, `properties.py`, `base.py`, `descriptor_builder.py`, `registry.py`, `factory.py`, `moddle.py`, `__init__.py`: `Moddle`, `create`, `create_any`, `get_type`, `get_element_descriptor`, `get_property_descriptor`, `get_type_descriptor`, `has_type`, `Base.get/set`, `type_`/`attrs_`/`parent_`/`descriptor_`/`model_`/`instance_of`, `isVirtual`/`replaces`/`redefines`, default values, `isMany` collections, generic (`isGeneric`) elements.
  - [ ] Keyword-named properties (`from`, `import`) and `type` reachable only via `get`/`set`/`**kwargs`.
  - [ ] Iterative descriptor building and property traversal.
  - [ ] `tests/moddle/test_*.py`: claim every case of `tests/upstream/moddle/spec/**` (schema.js adapted with `jsonschema` + vendored `tests/upstream/moddle-resources/schema/moddle.json`).
  - [ ] Lot gate (same checklist as Lot 0)

- [ ] **Lot 4 — moddle-xml Reader**
  - [ ] `src/bpmn_py/moddle_xml/common.py`, `read.py`: `Reader`, `ElementHandler`/`RootElementHandler`/`GenericElementHandler`/`ValueHandler`/`ReferenceHandler`, `Context` (`references`, `warnings`, `elements_by_id`), `xsi:type` dispatch, namespace prefix redefinition/collision, `$attrs` for unknown attributes, body properties, reference resolution post-pass, `ParseError` carrying warnings, lax mode.
  - [ ] Synchronous `from_xml(xml, type_name, options) -> ParseResult` (dataclass).
  - [ ] `tests/moddle_xml/test_reader.py`: claim all 86 cases of `tests/upstream/moddle-xml/spec/reader.js` with the upstream fixtures.
  - [ ] Lot gate (same checklist as Lot 0)

- [ ] **Lot 5 — moddle-xml Writer & roundtrip**
  - [ ] `src/bpmn_py/moddle_xml/write.py`: `Writer`, element/attribute/body serializers, namespace collection and declaration order, `xsi:type` and `serialize: property`, escaping, `format` indentation, `preamble`, number formatting via `_js.number_to_string`; iterative.
  - [ ] `to_xml(element, format=False, preamble=True) -> WriteResult`.
  - [ ] `tests/moddle_xml/test_writer.py`, `test_roundtrip.py`, `test_roundtrip_uml.py`, `test_performance.py` (depth 50 000 / ns depth 1 500, timeout adapted per runner): claim every case of `tests/upstream/moddle-xml/spec/*.js` and `integration/*`.
  - [ ] Lot gate (same checklist as Lot 0)

- [ ] **Lot 6 — bpmn-moddle**
  - [ ] `src/bpmn_py/bpmn_moddle/bpmn_moddle.py`, `simple.py`, `__init__.py`: `BpmnModdle` wiring the vendored descriptors (bpmn, bpmndi, dc, di, bioc) and additional packages, `from_xml`/`to_xml` delegates; public re-exports in `bpmn_py/__init__.py`.
  - [ ] `tests/bpmn_moddle/test_bpmn_moddle.py`, `xml/test_read.py`, `xml/test_write.py`, `xml/test_roundtrip.py`, `xml/test_edit.py`, `xml/test_expr.py`, `extension/test_*.py`, `integration/test_camunda.py`, `integration/test_misc.py`: claim every case of `tests/upstream/bpmn-moddle/spec/**` and `integration/**`; `validate(xml)` adapted through lxml + the OMG XSDs vendored under `tests/upstream/bpmn-moddle/fixtures/xsd` (every Xerces/libxml2 divergence recorded in the test docstring); `distro.cjs` claimed N-A, replaced by `tests/test_wheel_smoke.py` (install built wheel in a temp venv, import, roundtrip `simple.bpmn`).
  - [ ] `check(xml | element) -> Report` (L0 integrity: warnings, unresolved references, unknown attributes) in `src/bpmn_py/check.py` + tests.
  - [ ] Lot gate (same checklist as Lot 0)

- [ ] **Lot 7 — Node oracle (byte-identical XML)**
  - [ ] `tests/oracle/dump.mjs`: canonical dumper of a parsed model (`$type`, properties in descriptor order, references by id, `$attrs` key order) + `toXML({format:true})` for a fixture path; `tests/oracle/ledger.mjs`: mocha dry-run of the pinned upstream suites (dynamic cases included) → `tests/upstream/LEDGER.json`.
  - [ ] `tests/oracle/test_differential.py`: for every `.bpmn` fixture of bpmn-moddle and moddle-xml, compare the Python canonical dump and the byte-exact `to_xml(format=True)` output with the Node ones; warnings compared as lists.
  - [ ] `scripts/port_coverage.py`: read `tests/upstream/LEDGER.json` when present (dynamic cases), keep the static scan as fallback; CI oracle job regenerates and checks the ledger.
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle` green locally and in CI

- [ ] **Lot 8 — bpmn-auto-layout**
  - [ ] `src/bpmn_py/auto_layout/grid.py`, `layouter.py`, `handlers/*.py`, `di/*.py`, `utils/*.py`, `__init__.py`: `layout_process(xml: str) -> str` (1.3.0 semantics), `LayoutError`/`LayoutWarning`.
  - [ ] `tests/auto_layout/test_layout.py`: one claimed case per fixture (47) of `tests/upstream/bpmn-auto-layout/fixtures`, byte-exact against `tests/upstream/bpmn-auto-layout/snapshots`; oracle differential for every fixture.
  - [ ] UAT checkpoint: owner runs `layout_process` on a Camunda Modeler export without DI and opens the result in Camunda Modeler / bpmn-js.
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 9 — Typing, CLI, docs**
  - [ ] `scripts/gen_stubs.py` → `src/bpmn_py/bpmn_moddle/types.pyi` (all descriptor types, `create` overloads on `Literal["bpmn:..."]`, `is_a` narrowing); `stubtest` + `assert_type` tests; CI step.
  - [ ] `src/bpmn_py/cli.py` (`bpmn-py check|roundtrip|layout <file> [--json]`, stable exit codes) + `[project.scripts]` (conditional path: `pyproject.toml`, BR01-EX1) + tests.
  - [ ] README: real usage (read, check, build, write, layout, CLI), API table, "unofficial" notice; `docs/porting.md` (how a module maps to upstream, how to resync); `CHANGELOG.md` 0.1.0 entry.
  - [ ] UAT checkpoint: owner runs the CLI on a real file.
  - [ ] Lot gate (same checklist as Lot 0)

- [ ] **Lot 10 — Release readiness**
  - [ ] `scripts/port_coverage.py --strict` in CI (conditional path `.github/workflows/ci.yml`, BR01-EX2); 100 % of upstream cases claimed.
  - [ ] `tests/test_wheel_smoke.py` in CI build job.
  - [ ] Update `spec/SPEC_EVOL_BPMN_PY.md` § 2 with any deviation recorded during the port (D12 name resolved by the owner).
  - [ ] Version `0.1.0` (`uv version 0.1.0`), CHANGELOG finalised; owner configures the PyPI trusted publisher (pending publisher: repo `rhanka/bpmn-py`, workflow `release.yml`, environment `pypi`) — owner action.
  - [ ] Push branch, open PR `port-v1` → `main`, CI green, merge commit (NO squash, NO rebase), preserve branch, tag `v0.1.0` on `main` — owner action for the tag.
  - [ ] Move this file to `plan/done/01-BRANCH_port-v1.md`.
