# SPEC EVOL — bpmn-io

Status: EVOL (committed design, numbered decisions, ready to plan).
Date: 2026-09-22. Ladder: STUDY (`SPEC_STUDY_BPMN_MODDLE_PY.md`) → VOL (§1) → EVOL (§2–§6).
Peer review: three independent adversarial reviews — lens A (Claude Opus: maintainability /
packaging / user value), lens B (Claude Opus: correctness / licensing / interoperability), lens C
(Muse 1.3, effort max: plan executability, tooling, CI/release) — reconciled in §5. A Codex review
was launched but its result could not be retrieved in-session (status: `not covered`).

## 1. Volition (owner direction, reversible until the first release)

- One public Python library, **`bpmn-io`** (import `bpmn_io`), MIT, published under the owner's own
  PyPI account from GitHub `rhanka/bpmn-io-py`.
- **Literal transposition** of bpmn.io's `bpmn-moddle` stack and `bpmn-auto-layout`: algorithms
  *and* 100 % of the upstream test-suites, ported one-to-one, with attribution. The STUDY's phrase
  "0 % derivation" is withdrawn: the port is a derivative work distributed under MIT with the
  upstream notices preserved.
- Purpose: a pure-Python BPMN toolchain for Python AI agents (Google ADK and others), so an agent can
  draft, check, lay out and emit valid BPMN 2.0 XML without Node.
- Post-v1 candidates (recorded, not planned): backend-only, isometric parts of `bpmn-js`
  (import tree walker, ModelUtil/DiUtil/LabelUtil, BpmnRules) and `bpmnlint` (bpmn-io, MIT, 29
  built-in rules evaluated on the bpmn-moddle model), same literal-port method.

## 2. Decisions

**D1 — Scope of the transposition (v1).** `saxen` 11.2.0, the used subset of `min-dash` 5.1.0,
`moddle` 8.2.1, `moddle-xml` 12.3.1, `bpmn-moddle` 10.3.1, `bpmn-auto-layout` 1.3.0. Pinned in
`UPSTREAM.toml` (tag + commit + per-file sha256 in `UPSTREAM.lock`). Rationale: peer B showed that
expat cannot reproduce saxen's lenient parsing, warnings and positions that ~20 upstream tests assert;
porting saxen keeps the 100 % target and removes any XML dependency.

**D2 — Package layout.** One distribution, one import root, modules mirroring upstream:
`bpmn_io/_min_dash.py`, `bpmn_io/saxen/`, `bpmn_io/moddle/`, `bpmn_io/moddle_xml/`,
`bpmn_io/bpmn_moddle/`, `bpmn_io/auto_layout/`, plus `bpmn_io/__init__.py` re-exporting the public
API (`BpmnModdle`, `layout_process`, errors). Every ported module starts with
`# Transposed from <repo>@<version> <path> (MIT).` (version pin, not commit sha —
as-built deviation recorded in Lot 10).

**D3 — Naming rules (JS → Python), deterministic and documented in `docs/naming.md`.**
- Functions, methods, variables: camelCase → snake_case (`fromXML` → `from_xml`, `getType` →
  `get_type`).
- Moddle *property* names stay exactly as upstream (they are the BPMN attribute names):
  `element.get("sourceRef")`, and attribute access `element.sourceRef` through `__getattr__`.
- **`$` members:** `$type` → `element.type_`, `$attrs` → `element.attrs_`,
  `$parent` → `element.parent_`, `$descriptor` → `element.descriptor_`, `$model` → `element.model_`,
  `$instanceOf` → `element.instance_of(...)`. Trailing underscore is the PEP 8 convention for
  reserved-name collisions; `get("$type")` also works. `type` without underscore is never used for
  `$type` because `type` is a real BPMN property on four types (`Relationship`,
  `ExtensionAttributeDefinition`, `CorrelationProperty`, `ResourceParameter`).
- Python keywords among properties (`from`, `import`): reachable only through `get`/`set`,
  `create(..., **{"from": x})` and `getattr`; never as bare attributes. `Assignment.from` is
  serialized with `xsi:type`, so the keyword rule is exercised by the writer roundtrip too.
- Dynamic attribute access (`__getattr__`) never intercepts dunder names, so `copy`, `pickle`,
  `hasattr` and debugger introspection behave normally.
- Errors: `LayoutError`, `LayoutWarning` keep their names; parse errors raise `ParseError` carrying
  `.warnings`.

**D4 — API shape.** Synchronous. `BpmnModdle.from_xml(xml: str, type_name="bpmn:Definitions",
options=None) -> ParseResult` (dataclass: `root_element`, `references`, `warnings`,
`elements_by_id`). `to_xml(element, options=None) -> SerializationResult` (`xml`; as-built
name — the draft said `WriteResult`). `create(descriptor, attrs=None)` (mapping form, not
`**properties`, because descriptor properties include Python keywords like `from`),
`create_any`, `get_type`, `get_element_descriptor`, `has_type`,
`get_property_descriptor`. `layout_process(xml: str) -> str` (as 1.3.0). No async API.

**D4.1 — Async → sync mapping (mechanical, counts as *ported*).** Upstream `await
moddle.fromXML(xml)` → `moddle.from_xml(xml)`; a rejected promise → a raised exception:
`ParseError` for reader failures (carrying `.warnings`, as upstream attaches `err.warnings`),
`LayoutError` for layout failures. Test idioms map one-to-one: `await expect(p).to.be.rejectedWith(...)`
and `try { await … } catch (err) { … }` → `with pytest.raises(ParseError) as info:` followed by the
same assertions on `info.value`. Chai matchers map mechanically (`to.eql` → `json_equal`/`==`,
`to.match` → `re.search`, `to.contain` → `in`, `to.have.length` → `len`). These mappings are listed
in `docs/naming.md` § test idioms; a test that uses only them is *ported*, not *adapted*.

**D5 — JS semantics module.** `bpmn_io/_js.py` implements, with tests, the JS behaviours the port
relies on: truthiness, `undefined`/`null` distinction, `Math.round` (half-up), number formatting
(`100` not `100.0`, `1e21`, `1e-7`), `parseInt`/`parseFloat` leniency, insertion-ordered sets (dict),
`JSON.stringify` semantics for the `jsonEqual` matcher. Reader, writer and matchers are iterative
(upstream tests nest 50 000 levels; Python recursion limit is 1 000).

**D6 — Test port protocol.** Each upstream `it()` is claimed by one Python test via
`@pytest.mark.upstream("<file>", "<title>")`; `scripts/port_coverage.py --strict` is the CI gate
once 100 % is reached. Statuses: *ported* (literal), *adapted* (documented deviation, e.g. XSD
validation through lxml instead of Java Xerces; Ajv → `jsonschema`), *N-A* (claimed by a
`pytest.skip` test stating the reason, e.g. `distro.cjs` bundle tests replaced by an
install-from-wheel smoke test). Dynamic upstream cases (one per fixture in `LayoutSpec.js`, one
per schema in `schema.js`) are enumerated by a small mocha dry-run in the oracle job and written to
`tests/upstream/LEDGER.json`; the coverage script reads the ledger when present and, without it,
expands the `LayoutSpec.js` template from the fixture files. The scan covers `.js`, `.cjs`,
`.mjs` and `.ts` upstream files and the `iit(...)` wrapper. The ledger and the oracle harness are
built first (plan Lot 1), so byte-parity feedback exists from the first ported module on.

**D7 — Differential oracle.** `tests/oracle/` pins the JS packages (`npm ci --ignore-scripts`);
`@pytest.mark.oracle` tests run a canonical dumper (`$type`, properties in descriptor order,
references by id, `$attrs` key order) on both sides for every fixture and compare `toXML(format)`
byte-for-byte. Dependabot on `tests/oracle/package.json` is the "upstream moved" signal.

**D8 — Typing.** `py.typed`; generated `.pyi` stubs for all descriptor types, `create`
overloads on `Literal["bpmn:Task"]`, `is_a()` narrowing. Generator in `scripts/gen_stubs.py`,
checked in CI with `mypy --strict` and `stubtest`. As-built deviation (Lot 9): upstream ships
no `.d.ts` (`bpmn-moddle`, `bpmn-auto-layout` have none), so the stub surface is a new
Python-side design generated from the six vendored descriptors, not a mirror. No Pythonic
façade in v1.

**D9 — Validation levels.** L0 `check(xml | element) -> Report` = upstream integrity (parse
warnings, unresolved references, unknown attributes) — never called "validate". L1 (XSD validation
of emitted XML) exists only inside the test-suite, through lxml against the OMG XSDs vendored with
the upstream fixtures, as the adaptation of upstream's Java `xsd-schema-validator` calls; every
Xerces/libxml2 divergence is recorded in a divergence matrix (`docs/xsd-divergences.md`). No
runtime L1 API and no `[xsd]` extra in v1. L2 (semantic rules) is out of scope for v1; `bpmnlint`
(bpmn-io, MIT, 29 rules on the bpmn-moddle model) is the recorded post-v1 candidate.

**D10 — CLI.** `bpmn-io check|roundtrip|layout <file>` on argparse, `--json`, stable exit codes.

**D11 — Packaging & release.** hatchling, PEP 639 license expression + license files, PEP 735
dependency groups, Python ≥ 3.11, CI matrix 3.11–3.14 (ubuntu; 3.13 on windows/macos), actions
pinned by SHA + zizmor, Dependabot (github-actions, uv, npm). Tag `vX.Y.Z` = pyproject version →
build → PyPI Trusted Publishing (environment `pypi`, PEP 740 attestations) → GitHub release.
Keep-a-Changelog maintained by hand.

**D12 — Naming on PyPI (resolved by the owner, 2026-09-23).** Distribution name `bpmn-io`,
repo `rhanka/bpmn-io-py`, import package `bpmn_io` (dist and import names differ). `bpmn-py` is
registered on PyPI by another author (0.0.2, June 2024, sample-project metadata), which ruled it
out. On 2026-09-23 the PyPI JSON API returned 404 for `bpmn-io` (appears free; to confirm at
publish time). Risk recorded: the dist name matches the upstream organisation name while the
project states it is unofficial and unaffiliated (D13); if PyPI disputes the name, fall back to a
distinct name and keep `bpmn_io` as import name.

**D13 — Licensing.** `LICENSE` carries the owner's and the upstream copyright lines;
`THIRD_PARTY_NOTICES.md` lists every upstream project, holder, version and what is transposed; both
ship in the wheel. README and PyPI description state "unofficial, not affiliated with bpmn.io or
Camunda". OMG XSDs and test fixtures never ship in the wheel.

**D14 — Security.** The saxen port ignores DTDs, resolves no external entity, expands only built-in
and numeric character references; explicit tests for XXE payloads, entity amplification and deep
nesting (upstream advisory GHSA-x3vc-q6mj-47vp). Pre-release cyber-review hardening: the reader
drops extension attributes colliding with generic-element internals (`model_`, `type_`, `get`, … —
unreachable upstream, reachable through the `xxx_` renaming); import warnings are capped at 1000
with a truncation marker; the CLI sanitizes control characters in diagnostics and maps output
failures to exit 1. `twine` is hash-pinned in CI (`scripts/twine-check.txt`).

## 3. Architecture

```
bpmn_io/
  _js.py            JS semantics helpers (D5)
  _min_dash.py      transposed min-dash subset
  saxen/            Parser (lenient SAX, namespaces, entity decoding, positions)
  moddle/           Base, Factory, Registry, DescriptorBuilder, Properties, ns, Moddle
  moddle_xml/       Reader (ElementHandler tree, references, warnings), Writer (formatting, ns)
  bpmn_moddle/      BpmnModdle (descriptor wiring, from_xml/to_xml), descriptors loader
  auto_layout/      Grid, Layouter, handlers, DI factory, layout_process
  cli.py            argparse entry point (D10)
  resources/        vendored descriptors
```
Data flow: XML → saxen events → moddle-xml Reader builds moddle elements from descriptors → references
resolved in a post-pass → `ParseResult`. Writing: element tree → Writer walks descriptors → XML text.
Layout: `from_xml` → Layouter grid → DI elements created through moddle → `to_xml`.

## 4. Testing

- Unit: ported upstream suites (the static count is printed by `scripts/port_coverage.py`; the
  ledger adds the dynamic cases), organised as `tests/<pkg>/test_<spec>.py` mirroring upstream file
  names.
- Golden: upstream fixtures and auto-layout snapshots (byte-exact `toXML`), with a byte-comparison
  gate in every lot that touches serialization (writer, bpmn-moddle, auto-layout).
- Property: hypothesis roundtrip on generated models (small, complements the oracle; plan Lot 6).
- Oracle: Node differential (D7), mandatory in CI, skipped locally without `node_modules`.
- Gates: ruff, mypy strict, stubtest, `sync_upstream --check`, `port_coverage --strict` (at 100 %),
  wheel/sdist `twine check`, install-from-wheel smoke.

## 5. Peer reconciliation

| Topic | Lens A | Lens B | Decision |
|---|---|---|---|
| XML parser | expat direct, harden | expat cannot match saxen; port saxen | D1: port saxen |
| Test helpers | — | must vendor helper.js/expect.js | done in UPSTREAM.toml |
| Test count | — | static count unreliable, use mocha dry-run | D6 ledger |
| Typed stubs | mandatory in v1 | — | D8 |
| CLI | v1, argparse | — | D10 |
| Auto-layout priority | key adoption driver, v1 | — | v1 (D1), 1.3.0 |
| Naming `bpmn-moddle` on PyPI | perceived official | `bpmn-py` taken | D12 resolved (`bpmn-io`) |
| Workspace / 2 dists | fine | contradicts single dist | single dist (owner) |
| Number/round semantics | — | acceptance criteria | D5 |

Lens C (Muse, on the plan and tooling), reconciled:

| Finding | Decision |
|---|---|
| Release assumes an unresolved PyPI name | D12 stays with the owner; release workflow reads the name from `pyproject.toml`, runs the full suite, `--strict` coverage and a wheel smoke before publishing |
| CI ignored the working branch | CI runs on `main` and `port-*` pushes |
| Coverage scanner missed `iit`, `.cjs`, `.ts`, dynamic titles | scanner extended; ledger first (D6) |
| Async → sync unspecified | D4.1 |
| Oracle too late | plan re-sequenced: oracle harness is Lot 1 |
| Port source (`lib/`) had no provenance | upstream `lib/` trees vendored and sha256-pinned next to `test/` |
| L1 XSD promised without a lot | D9 narrowed to the test-suite adaptation |
| `jsonschema`, hypothesis, `xmi:type`, saxen streaming API, `from`/xsi:type unplanned | added to the lots |
| `sync_upstream.py` fetched movable tags, no extra-file detection | fetch by commit, `--check` verifies pins and extras, member paths sanitized |

## 6. Out of scope (v1)

bpmnlint rules (L2), bpmn-js backend parts, bpmn-auto-layout 2.0 (alpha, TS rewrite — re-port when
released), async API, Pythonic façade, docs site.
