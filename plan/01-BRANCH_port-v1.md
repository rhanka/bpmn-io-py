# Feature: bpmn-io v1 — literal port of the bpmn.io stack (moddle → bpmn-moddle → auto-layout)

## Objective
Transpose saxen, the used min-dash subset, moddle, moddle-xml, bpmn-moddle and bpmn-auto-layout to pure Python, one upstream file at a time, with 100 % of the upstream test-suites claimed and byte-identical XML output (`to_xml` and layout snapshots) verified against the pinned JS packages through the Node oracle. Design: `spec/SPEC_EVOL_BPMN_PY.md` (D1–D14).

## Scope / Guardrails
- Literal transposition: same file split, same function order and names (snake_case), same warnings and error texts; every ported module starts with `# Transposed from <repo>@<short-sha> <path> (MIT).`
- Vendored upstream trees (`tests/upstream/**`, `src/bpmn_io/resources/**`) are never edited by hand; `scripts/sync_upstream.py --check` must stay green.
- Every upstream `it()` is claimed with `@pytest.mark.upstream("<file>", "<title>")` (ported / adapted / N-A with reason); no test is dropped silently.
- Zero runtime dependency; `lxml` and `jsonschema` only in the `test` dependency group.
- Iterative (non-recursive) reader, writer and matchers; JS semantics only through `bpmn_io/_js.py`.
- Commit discipline: one logical change per commit, selective `git add <files>`, under ~150 lines per commit, lot checkboxes updated within the commit, NO attribution trailers of any kind (no `Co-Authored-By`, no `Generated with`, no session ids).
- Local gate before every push: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run python scripts/port_coverage.py`.
- All repository text in English.

## Branch Scope Boundaries (MANDATORY)
- **Allowed Paths (implementation scope)**:
  - `src/bpmn_io/**` (except `src/bpmn_io/resources/**`)
  - `tests/**` (except `tests/upstream/**`)
  - `scripts/**`
  - `docs/**`
  - `README.md`, `CHANGELOG.md`
  - `plan/01-BRANCH_port-v1.md`
- **Forbidden Paths (must not change in this branch)**:
  - `tests/upstream/**`, `src/bpmn_io/resources/**`, `UPSTREAM.lock` (regenerated only by `scripts/sync_upstream.py`)
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
- `acknowledge` BR01-R1: plan re-sequenced after the Muse 1.3 review (oracle first, vendored `lib/` sources, per-lot byte gates, D4.1 async mapping, L1 narrowed to tests).
- `acknowledge` BR01-D12: resolved 2026-09-23 — owner chose dist name `bpmn-io`, a new repo name under `rhanka`, import package `bpmn_io`; affects Lot 9 (CLI) and Lot 10 (release).
- `acknowledge` BR01-EX5: dist rename in `pyproject.toml` + `uv.lock` (name + repo URLs). Reason: owner rename decision. Impact: distribution identity only. Rollback: `git checkout -- pyproject.toml uv.lock`.
- `acknowledge` BR01-EX6: import-package path rename in `UPSTREAM.toml` + `UPSTREAM.lock` (dest path keys only). Reason: owner rename decision. Impact: paths only, sha256 digests unchanged, verified by `sync_upstream.py --check`. Rollback: `git checkout` both + move the package dir back.
- `acknowledge` BR01-EX7: name updates + D12 resolution in `spec/SPEC_EVOL_BPMN_PY.md`. Reason: owner rename decision. Impact: spec text. Rollback: `git checkout` the spec.
- `acknowledge` BR01-EX8: product-name + path updates in `THIRD_PARTY_NOTICES.md` (forbidden path). Reason: owner rename decision. Impact: header lines + one table cell. Rollback: `git checkout` the file.
- `acknowledge` BR01-EX9: rename fallout in `.github/workflows/*.yml` (smoke-test import), `tests/oracle/package.json` + `package-lock.json` (oracle name), `SECURITY.md`, `CONTRIBUTING.md`, `plan/BRIEF-port-v1.md`. Reason: owner rename decision. Impact: name references only. Rollback: `git checkout` the files.
- `blocked` BR01-PR: draft PR `port-v1` → `main` and `git push` pending: origin points to `rhanka/bpmn-io-py`, which does not exist yet (GitHub-side rename is an owner action), and this environment has no network egress. Recorded per BRIEF rule 8; unblocks the Lot 0 checkbox.
- `attention` BR01-COLOR: the default model needs a sixth descriptor package. Evidence: upstream `BpmnModdle` default (simple.js) wires `bpmn-in-color-moddle` (^0.2.0, devDependency bundled into dist) next to the five vendored sets; `bpmn-in-color.bpmn` (`color:` non-normative ns) is read with a zero-warning assertion (`BPMN in color properties`), which a five-package model cannot satisfy. The `extends`-bearing bioc traits (`ColoredEdge`, `ColoredShape`, skipped by the descriptor dump) do not cover it (different namespace). Actions when network exists: pin `bpmn-in-color-moddle` (resolve `^0.2.0`), add an `UPSTREAM.toml` section + vendored resources + oracle devDependency, wire it into Lot 7 `BpmnModdle`, amend EVOL D1. `example-colors.bpmn` (`bc` biocolors ns) roundtrips through `$attrs` and is unaffected.
- `acknowledge` BR01-EX1: `.github/workflows/ci.yml` oracle job regenerates the ledger and fails on drift (`node tests/oracle/ledger.mjs --check`); the generated `tests/upstream/LEDGER.json` is committed as the drift reference. Reason: Lot 1 oracle harness. Impact: CI only. Rollback: `git checkout` the workflow and delete `LEDGER.json`.

## Orchestration Mode (AI-selected)
- [x] **Mono-branch + cherry-pick** (default for orthogonal tasks; single final test cycle)
- [ ] **Multi-branch** (only if sub-workstreams require independent CI or long-running validation)
- Rationale: the lots are strictly sequential (each layer depends on the previous one); a single branch `port-v1` with small commits, a draft PR and CI on every push (`port-*` branches) is enough.

## UAT Management (in orchestration context)
- No UI. UAT = the owner runs the README quick-start against a real `.bpmn` (Camunda Modeler export) after Lot 8, and the CLI after Lot 9.
- UAT checkpoints listed as checkboxes inside the relevant lots.

## Plan / Todo (lot-based)
- [ ] **Lot 0 — Baseline & port protocol**
  - [ ] Read `spec/SPEC_EVOL_BPMN_PY.md`, `CONTRIBUTING.md`, `UPSTREAM.toml`; run the local gate once (green baseline); open a draft PR `port-v1` → `main` so every push is reviewed in CI.
  - [ ] Sources to transpose are the vendored upstream trees `tests/upstream/<pkg>/lib/**` (pinned commit, sha256 in `UPSTREAM.lock`); tests are `tests/upstream/<pkg>/test/**`. Never read a port source from anywhere else.
  - [ ] Write `docs/naming.md`: the JS → Python naming table of D3 (camelCase → snake_case, moddle property names unchanged, `$type` → `type_`, `$attrs` → `attrs_`, `$parent` → `parent_`, `$descriptor` → `descriptor_`, `$model` → `model_`, `$instanceOf` → `instance_of`, keyword properties via `get`/`set` only, dunder names never intercepted) and § test idioms (D4.1: await/reject → call/`pytest.raises`, chai → pytest).
  - [ ] `src/bpmn_io/_js.py` + `tests/test_js.py`: truthiness, `undefined`/`null` sentinel, `math_round` (half-up), `number_to_string` (JS `Number#toString`: `100`, `1e+21`, `1e-7`), `parse_int`/`parse_float` leniency, ordered set, `json_stringify` semantics.
  - [ ] `tests/conftest.py`: `upstream_dir(pkg)` / `read_fixture(pkg, path)` helpers.
  - [ ] `tests/_matchers.py`: transposed `expect.js` / `matchers.js` of moddle-xml and bpmn-moddle (`json_equal` excluding `$parent`/`$model`/`$descriptor`, insertion order kept, iterative).
  - [ ] Lot gate:
    - [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy`
    - [ ] `uv run pytest`
    - [ ] `uv run python scripts/port_coverage.py` runs clean (no stale/duplicate claims)

- [x] **Lot 1 — Node oracle harness & test ledger (first, so parity is measured from Lot 2 on)**
  - [ ] `tests/oracle/ledger.mjs`: mocha `--dry-run --reporter json` over each vendored upstream suite (with the pinned oracle packages) → `tests/upstream/LEDGER.json` (`{"<file>": ["<full title>", ...]}`); `scripts/port_coverage.py` already reads it; CI oracle job regenerates it and fails on drift (BR01-EX1: `.github/workflows/ci.yml`).
  - [ ] `tests/oracle/run.mjs`: generic runner — given a package, a function path and JSON args, returns JSON results (saxen event streams, moddle canonical dumps, `toXML` strings, `layoutProcess` output).
  - [ ] `tests/oracle/dump.mjs`: canonical model dumper (`$type`, properties in descriptor order, references by id, `$attrs` key order) shared by all later lots.
  - [ ] `tests/oracle/conftest.py` + `tests/oracle/_bridge.py`: pytest fixture calling the runner through `node` (skip locally without `node_modules`, mandatory in CI).
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 2 — min-dash subset**
  - [ ] Inventory every min-dash import in `tests/upstream/{saxen,moddle,moddle-xml,bpmn-moddle,bpmn-auto-layout}/lib/**` → list in `docs/naming.md` § min-dash.
  - [ ] `src/bpmn_io/_min_dash.py`: transpose exactly those helpers from `tests/upstream/min-dash/lib/**`, same semantics on dict/list, insertion order kept.
  - [ ] `tests/min_dash/test_*.py`: claim every case of `tests/upstream/min-dash/test/**` — ported for the transposed helpers; N-A with reason for helpers not used by the ported libraries, for `integration/bundle.spec.{js,cjs}` (JS bundle packaging) and `index.spec.ts` (TypeScript typing tests).
  - [ ] Oracle: differential test on each transposed helper for a table of inputs.
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 3 — saxen (lenient SAX parser)**
  - [ ] `src/bpmn_io/saxen/parser.py` (+ `decode.py`): `Parser` with `on(...)` handlers, `ns()` namespace mode, `parse()`, and the streaming API (`write(chunk)` chainable, `end()` returning the error), entity decoding, attribute parsing leniency and warning texts, positions (line/column as upstream), error texts, `proxy`/`ns` modes, stop/skip control.
  - [ ] Security: no DTD processing, no external entities, only built-in and numeric character references; explicit tests (XXE payload, entity amplification, deep nesting GHSA-x3vc-q6mj-47vp).
  - [ ] `tests/saxen/test_parser.py`, `test_elements.py`, `test_decode.py`, `test_errors.py`, `test_modes.py`, `test_stream.py`: claim every case of `tests/upstream/saxen/test/**`; `test/perf` claimed adapted (timeout per CI runner) or N-A with reason.
  - [ ] Oracle: event-stream differential (every event, attribute map, warning and position) for every `.bpmn`/`.xml` fixture of moddle-xml and bpmn-moddle.
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 4 — moddle (meta-model runtime)**
  - [ ] `src/bpmn_io/moddle/ns.py`, `types.py`, `properties.py`, `base.py`, `descriptor_builder.py`, `registry.py`, `factory.py`, `moddle.py`, `__init__.py`: `Moddle`, `create`, `create_any`, `get_type`, `get_element_descriptor`, `get_property_descriptor`, `get_type_descriptor`, `has_type`, `Base.get/set`, `type_`/`attrs_`/`parent_`/`descriptor_`/`model_`/`instance_of`, `isVirtual`/`replaces`/`redefines`, default values, `isMany` collections, generic (`isGeneric`) elements; `__getattr__` never intercepts dunders (tests with `copy`, `pickle`, `hasattr`).
  - [ ] Keyword-named properties (`from`, `import`) and `type` (4 BPMN types) reachable only via `get`/`set`/`**kwargs`.
  - [ ] Iterative descriptor building and property traversal.
  - [ ] `tests/moddle/test_*.py`: claim every case of `tests/upstream/moddle/test/spec/**` (schema.js adapted with `jsonschema` against `tests/upstream/moddle/resources/schema/moddle.json`, one case per model fixture).
  - [ ] Oracle: canonical descriptor dump (effective properties per type, in order) for every type of every vendored descriptor.
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 5 — moddle-xml Reader**
  - [ ] `src/bpmn_io/moddle_xml/common.py`, `read.py`: `Reader`, `ElementHandler`/`RootElementHandler`/`GenericElementHandler`/`ValueHandler`/`ReferenceHandler`, `Context` (`references`, `warnings`, `elements_by_id`), `xsi:type` **and `xmi:type`** dispatch, namespace prefix redefinition/collision, `$attrs` for unknown attributes, body properties, reference resolution post-pass, `ParseError` carrying warnings (D4.1), lax mode.
  - [ ] Synchronous `from_xml(xml, type_name, options) -> ParseResult` (dataclass).
  - [ ] `tests/moddle_xml/test_reader.py`: claim every case of `tests/upstream/moddle-xml/test/spec/reader.js` with the upstream fixtures.
  - [ ] Oracle: canonical dump + warnings list equal for every moddle-xml and bpmn-moddle fixture.
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 6 — moddle-xml Writer & roundtrip**
  - [ ] `src/bpmn_io/moddle_xml/write.py`: `Writer`, element/attribute/body serializers, namespace collection and declaration order, `xsi:type` and `serialize: property` (incl. `Assignment.from`), escaping table, `format` indentation, `preamble`, number formatting via `_js.number_to_string`; iterative.
  - [ ] `to_xml(element, format=False, preamble=True) -> WriteResult`.
  - [ ] `tests/moddle_xml/test_writer.py`, `test_roundtrip.py`, `test_roundtrip_uml.py`, `test_performance.py` (depth 50 000 / ns depth 1 500, timeout adapted per runner): claim every case of `tests/upstream/moddle-xml/test/spec/*.js` and `test/integration/*`.
  - [ ] Byte gate: `to_xml(format=True)` and `to_xml(format=False)` byte-identical to the oracle for every moddle-xml fixture.
  - [ ] Property tests (hypothesis): generated models roundtrip `from_xml(to_xml(m))` to an equal canonical dump.
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 7 — bpmn-moddle**
  - [ ] `src/bpmn_io/bpmn_moddle/bpmn_moddle.py`, `simple.py`, `__init__.py`: `BpmnModdle` wiring the vendored descriptors (bpmn, bpmndi, dc, di, bioc) and additional packages, `from_xml`/`to_xml` delegates; public re-exports in `bpmn_io/__init__.py`.
  - [ ] `tests/bpmn_moddle/test_bpmn_moddle.py`, `xml/test_read.py`, `xml/test_write.py`, `xml/test_roundtrip.py`, `xml/test_edit.py`, `xml/test_expr.py`, `extension/test_*.py`, `integration/test_camunda.py`, `integration/test_misc.py`: claim every case of `tests/upstream/bpmn-moddle/test/spec/**` and `test/integration/**`; `validate(xml)` adapted through lxml against the OMG XSDs vendored with the upstream fixtures, every Xerces/libxml2 divergence recorded in `docs/xsd-divergences.md`; `distro.cjs` claimed N-A, replaced by the CI wheel smoke test.
  - [ ] `check(xml | element) -> Report` (L0 integrity: warnings, unresolved references, unknown attributes) in `src/bpmn_io/check.py` + tests.
  - [ ] Byte gate: `to_xml` byte-identical to the oracle for every bpmn-moddle fixture (incl. `complex.bpmn`, vendor exports, extension fixtures).
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 8 — bpmn-auto-layout**
  - [ ] `src/bpmn_io/auto_layout/grid.py`, `layouter.py`, `handlers/*.py`, `di/*.py`, `utils/*.py`, `__init__.py` from `tests/upstream/bpmn-auto-layout/lib/**`: `layout_process(xml: str) -> str` (1.3.0 semantics), `LayoutError`/`LayoutWarning`; `Math.round` via `_js.math_round` only.
  - [ ] `tests/auto_layout/test_layout.py`: one claimed case per fixture (47) of `tests/upstream/bpmn-auto-layout/test/fixtures`, byte-exact against `test/snapshots`.
  - [ ] Byte gate: oracle differential for every fixture.
  - [ ] UAT checkpoint: owner runs `layout_process` on a Camunda Modeler export without DI and opens the result in Camunda Modeler / bpmn-js.
  - [ ] Lot gate (same checklist as Lot 0) + `uv run pytest -m oracle`

- [ ] **Lot 9 — Typing, CLI, docs**
  - [ ] `scripts/gen_stubs.py` → `src/bpmn_io/bpmn_moddle/types.pyi` (all descriptor types, `create` overloads on `Literal["bpmn:..."]`, `is_a` narrowing); `stubtest` + `assert_type` tests; CI step (BR01-EX2).
  - [ ] `src/bpmn_io/cli.py` (`bpmn-io check|roundtrip|layout <file> [--json]`, stable exit codes) + `[project.scripts]` (conditional path: `pyproject.toml`, BR01-EX3) + tests.
  - [ ] README: real usage (read, check, build, write, layout, CLI), API table, "unofficial" notice; `docs/porting.md` (how a module maps to upstream, how to resync); `CHANGELOG.md` 0.1.0 entry.
  - [ ] UAT checkpoint: owner runs the CLI on a real file.
  - [ ] Lot gate (same checklist as Lot 0)

- [ ] **Lot 10 — Release readiness**
  - [ ] `scripts/port_coverage.py --strict` in CI (BR01-EX4: `.github/workflows/ci.yml`); 100 % of upstream cases claimed, no unresolved dynamic title.
  - [ ] Update `spec/SPEC_EVOL_BPMN_PY.md` § 2 with any deviation recorded during the port (D12 name resolved by the owner).
  - [ ] Version `0.1.0` (`uv version 0.1.0`), CHANGELOG finalised; owner configures the PyPI trusted publisher (pending publisher: repo `rhanka/bpmn-io-py`, workflow `release.yml`, environment `pypi`) — owner action; rehearsal on TestPyPI recommended.
  - [ ] Mark the PR ready, CI green, merge commit (NO squash, NO rebase), preserve branch, tag `v0.1.0` on `main` — owner action for the tag.
  - [ ] Move this file to `plan/done/01-BRANCH_port-v1.md`.
