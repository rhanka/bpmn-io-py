# SPEC STUDY — bpmn-moddle-py

Status: STUDY (open question, options, trade-offs — no commitment).
Date: 2026-09-22. Ladder: STUDY → VOL → EVOL.

## 1. Intent (owner statement, condensed)

Create and publish a Python library that is a 100 % mapped port of bpmn.io `bpmn-moddle`, so that
Python code can natively manipulate the bpmn-moddle object model (the "AST"), validate the integrity
of a BPMN document, and emit BPMN 2.0 XML — without going through TypeScript/Node. MIT licensed,
public, with "0 % derivation". Possibly also port `bpmn-auto-layout` in the same library.
Everything is to be created: repository, serious publication of the Python package(s), maintenance
facilitation.

## 2. Facts established (upstream, 2026-09-22)

| Package | Version | License | Role | Runtime deps |
|---|---|---|---|---|
| bpmn-moddle | 10.3.1 | MIT (camunda Services GmbH, 2014) | thin wrapper: `Moddle` + `Reader/Writer` wiring + descriptors | moddle, moddle-xml, min-dash |
| moddle | 8.2.1 | MIT | meta-model runtime: registry, descriptor builder, factory, `Base` element, ns handling | min-dash |
| moddle-xml | 12.3.1 | MIT | XML reader/writer driven by descriptors | saxen (SAX), min-dash |
| bpmn-auto-layout | 1.3.0 (2.0.0-alpha on main, TS) | MIT | generates BPMNDI for a diagram with or without DI; `layoutProcess(xml) → {xml, warnings}` | bpmn-moddle ^10, min-dash |

Descriptors shipped by bpmn-moddle (`resources/`):

| File | prefix | types | enums | notes |
|---|---|---|---|---|
| bpmn/json/bpmn.json | bpmn | 137 | 9 | `xml: {tagAlias: lowerCase, typePrefix: t}`; generated upstream from OMG CMOF |
| bpmn/json/bpmndi.json | bpmndi | 6 | 2 | |
| bpmn/json/dc.json | dc | 7 | 0 | |
| bpmn/json/di.json | di | 11 | 0 | `xml: {tagAlias: lowerCase}` |
| bpmn-io/json/bioc.json | bioc | 2 | 0 | bpmn.io colour extension |
| bpmn/xsd/*.xsd | — | — | — | OMG BPMN 2.0 XSDs (Semantic, BPMN20, BPMNDI, DC, DI) |

Descriptor vocabulary actually used by bpmn.json (the contract a runtime must honour):
type keys `name, superClass, properties, isAbstract`; property keys
`name, type, isAttr, isMany, isReference, isId, isBody, isVirtual, default, replaces, xml.serialize ∈ {property, xsi:type}`.
Primitive types: `String, Boolean, Integer, Real, Element`. Cross-package types: `bpmndi:BPMNDiagram` etc.

moddle-xml behaviours that define "100 % mapped" (from dist inspection):
`fromXML → {rootElement, references, warnings, elementsById}`; unknown elements become generic
(`createAny`, `$instanceOf`), unresolved references become warnings, `xsi:type` dispatch, `$attrs` for
unknown attributes, `$parent` back-links, namespace prefix redefinition/collision handling.
Upstream test corpus: 67 BPMN fixtures under `test/fixtures/bpmn` (MIT), plus an XSD validation suite
(requires Java upstream).

bpmn-moddle does **not** perform semantic validation. "Integrity" upstream means: parse succeeds,
all references resolve, no unknown attributes/elements in known namespaces (warnings), roundtrip is
lossless. Semantic rules (e.g. "process has a start event") live in `bpmnlint`, a separate project.

PyPI availability (2026-09-22): `bpmn-moddle`, `bpmn_moddle`, `moddle`, `bpmn-auto-layout` free;
`bpmn`, `pybpmn` taken.

Local tooling: Python 3.14.4, uv 0.11.24. Owner rule: no Python in sentropic repos/jobs — this
project is a standalone public library, outside that perimeter (to confirm, see Q8).

## 3. Open questions (owner decides)

- **Q1 — What does "0 % derivation" mean?**
  - (a) Clean-room: no JS code translated; only the *contract* (API names, descriptor semantics,
    warnings, XML output) is mapped. Descriptors regenerated from OMG sources, not copied.
  - (b) Data reuse: vendor the upstream JSON descriptors (MIT, attributed) as the interoperability
    contract; reimplement the runtime from scratch in Python.
  - (c) Faithful translation of the JS sources (a derived work, MIT-compatible with attribution).
  Stakes: (a) is the strongest IP posture but the descriptors are the *only* thing guaranteeing
  identical `$type`/property names and serialization; regenerating them risks silent divergence.
  (b) keeps 100 % mapping at zero risk and MIT explicitly permits it. (c) is fastest but contradicts
  "0 % derivation" as commonly read.
- **Q2 — Which validation levels?** L0 = moddle-level integrity (parse, references, warnings,
  roundtrip); L1 = XSD validation against OMG schemas; L2 = semantic rules à la bpmnlint.
- **Q3 — bpmn-auto-layout: same package, sibling package in the same repo, or out of v1?**
- **Q4 — API surface: mirror the JS API 1:1 (dynamic `create('bpmn:Task')`, `$type`, `get/set`),
  Pythonic generated classes, or dynamic core + generated typing stubs?**
- **Q5 — XML backend: stdlib only (zero deps) vs lxml (C dependency, fast, XSD validation built in).**
- **Q6 — Minimum Python version.** 3.10 reaches EOL 2026-10; 3.11 is supported until 2027-10.
- **Q7 — Distribution name and namespace.** `bpmn-moddle` on PyPI / `bpmn_moddle` import, or a name
  that avoids any confusion with bpmn.io (`pybpmn-moddle`, `bpmn-moddle-py`).
- **Q8 — Hosting.** GitHub owner/org for the public repository; PyPI account for trusted publishing.
- **Q9 — Test corpus.** Reuse upstream fixtures (MIT) as golden files, or write an independent corpus.
- **Q10 — Upstream oracle in CI.** Run Node `bpmn-moddle` in CI as a differential oracle (compare
  roundtrips and warnings) — strongest conformance guarantee, at the price of Node in CI only.

## 4. Approaches

### A — Faithful dynamic port (recommended)
Reimplement the moddle runtime in Python: `Registry` (descriptor builder, inheritance, `replaces`,
virtual properties), `Factory` (per-type generated classes with `$type`, `$descriptor`, `$attrs`,
`$parent`, `get/set`, `$instanceOf`), and a moddle-xml equivalent `Reader/Writer` on the stdlib
expat/ElementTree, driven by the same vendored descriptors. Public API mirrors JS
(`BpmnModdle().from_xml(xml) → ParseResult(root_element, references, warnings, elements_by_id)`,
`to_xml(element, format=True)`, `create('bpmn:Task', ...)`). Generated `.pyi` stubs give IDE typing.
- Pros: 100 % mapped by construction (same descriptors, same semantics, same warnings); extension
  namespaces (camunda, zeebe, bioc) plug in exactly as upstream; auto-layout port becomes natural.
- Cons: dynamic objects are less idiomatic; typing is stubs-only.

### B — Pythonic typed model (code-gen)
Generate frozen-ish dataclasses per descriptor type, with generated (de)serializers.
- Pros: idiomatic, statically typed, great IDE support.
- Cons: diverges from bpmn-moddle semantics (`$attrs`, generic elements, extension elements, `xsi:type`
  dispatch, reference resolution are awkward in a static model); a second serializer layer to keep
  in sync; "100 % mapped" becomes a claim rather than a property.

### C — Hybrid
A core + a generated typed façade. Pros: best of both; cons: two APIs to document and maintain — YAGNI
for v1. Can be added later on top of A without breaking changes.

## 5. Cross-cutting design points (apply to A)

- **Descriptor provenance ledger**: `resources/UPSTREAM.md` records upstream package, version, commit
  SHA and sha256 of each vendored descriptor; a CI job (`upstream-sync`) diffs vendored files
  against the pinned npm tarball and opens an issue when upstream moves.
- **Conformance suite**: upstream fixtures as golden files + roundtrip property tests + XSD validation
  of every emitted document (lxml in the *test* extra only).
- **Optional Node oracle** (Q10): `tests/oracle/` runs `bpmn-moddle` via `npx` and diffs JSON dumps
  of the parsed model; skipped when Node is absent, mandatory in CI.
- **Validation API**: `validate(xml | element) → Report(errors, warnings)` with L0 always on,
  L1 when the `[xsd]` extra (lxml) is installed, L2 as a separate future package.
- **Packaging**: `pyproject.toml` (hatchling), uv workspace, ruff + mypy strict + pytest, GitHub
  Actions matrix, PyPI trusted publishing (OIDC) on tag, `CHANGELOG.md`, semver independent of
  upstream but with `Upstream-Compat: bpmn-moddle 10.3.1` in metadata and README.
- **Licensing**: MIT for the port; `THIRD_PARTY_NOTICES.md` attributing bpmn.io/camunda for vendored
  descriptors and fixtures (if Q1 ≠ (a)); OMG XSDs kept only under `tests/` with their notice.
- **auto-layout** (Q3): sibling package `bpmn-auto-layout` in the same uv workspace, depending on
  `bpmn-moddle`, released on its own cadence — mirrors the upstream split, keeps the core lean.

## 6. Risks

- Upstream `moddle-xml` edge cases (namespace redefinition, prefix collision, `xsi:type`, generic
  elements) are numerous; the fixture corpus + oracle are the only credible guard.
- Name `bpmn-moddle` on PyPI could be perceived as official by users; mitigation: explicit
  "unofficial, not affiliated" notice, or a distinct name (Q7).
- bpmn-auto-layout 2.0 is in alpha upstream (TS rewrite); porting 1.3.0 now means re-porting soon.

## 7. Owner input received (2026-09-22, mid-study)

- **Q1 → (c) literal transposition** of upstream algorithms *and* tests, with full attribution to
  bpmn.io and MIT terms honouring the bpmn.io/camunda copyright notice. Any IP concern raised during
  the port gets an explicit review (see licensing ledger).
- **Naming**: owner suggests a simple name "like `bpmn-py`". `bpmn-py` and `bpmn_py` are already
  taken on PyPI; `bpmn-moddle`, `bpmn-auto-layout`, `bpmnpy` are free.
- **Publication**: under the owner's own PyPI account (to be created), GitHub owner `rhanka`.
- **Directive**: proceed to a complete, state-of-the-art scaffold of the library repository now;
  remaining questions (Q2–Q10) are decided by the agent on the recommended defaults and recorded in
  the VOL rung, reversible.
