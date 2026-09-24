# bpmn-io

**bpmn.io's `bpmn-moddle` and `bpmn-auto-layout`, transposed to pure Python.**

Read, check, build, lay out and write BPMN 2.0 XML from Python, with the exact object model and
semantics of the reference JavaScript implementation, and no runtime dependency.

> Status: the full port is implemented (moddle, moddle-xml, bpmn-moddle, bpmn-auto-layout)
> with byte-identical conformance gates; release 0.1.0 is in preparation. Nothing is published
> on PyPI yet.
>
> bpmn-io is an independent project, not affiliated with bpmn.io or Camunda.

## Why this exists

BPMN is a natural target for AI agents written in Python (Google ADK, LangGraph, plain SDK
agents, …): an agent can draft a process, check it, lay it out and hand a valid `.bpmn` file to a
human or to an engine. Until now the only faithful implementation of the BPMN 2.0 meta-model
(`bpmn-moddle`) and of automatic diagram layout (`bpmn-auto-layout`) lived in JavaScript, so a
Python agent had to shell out to Node or skip validation altogether.

bpmn-io removes that gap: a 100 % mapped Python port, so the objects, the warnings and the XML you
get are the ones bpmn-js, Camunda Modeler and the bpmn.io toolchain produce and expect.

## Design principles

- **Literal transposition.** Algorithms and test-suites of `moddle`, `moddle-xml`, `bpmn-moddle`
  and `bpmn-auto-layout` are ported one-to-one, at the pinned upstream versions listed in
  [`UPSTREAM.toml`](UPSTREAM.toml). Every upstream test case must be claimed by a Python test
  (`scripts/port_coverage.py`, enforced in CI).
- **Same descriptors.** The BPMN 2.0, DI, DC and bioc moddle descriptors are vendored verbatim
  (sha256-pinned in `UPSTREAM.lock`), so `$type` names, properties and serialization rules are
  identical.
- **Differential oracle.** CI also runs the upstream JavaScript packages through Node and compares
  canonical dumps and emitted XML with the Python port (`tests/oracle/`).
- **Zero runtime dependency.** The lenient SAX parser (`saxen`) is transposed too, so parsing
  behaviour, warnings and error positions match upstream exactly.
- **MIT, attributed.** See [`LICENSE`](LICENSE) and
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Usage

```python
from bpmn_io import BpmnModdle, check, layout_process

moddle = BpmnModdle()

# read
result = moddle.from_xml(xml)  # ParseResult(root_element, references, warnings, elements_by_id)
definitions = result.root_element

# check (L0 integrity: warnings, unresolved references, unknown attributes)
report = check(xml)
assert report.ok, report.errors

# build
task = moddle.create("bpmn:Task", {"name": "Review"})
definitions.get("rootElements")[0].get("flowElements").append(task)

# lay out (generates DI for diagrams without one)
laid_out = layout_process(xml)

# write
out = moddle.to_xml(definitions, {"format": True})
print(out.xml)
```

```bash
bpmn-io check process.bpmn            # exit 0 when clean, 1 on errors
bpmn-io check process.bpmn --json     # {"ok": true, "errors": [], "warnings": [], ...}
bpmn-io roundtrip process.bpmn        # parse + serialize back to stdout
bpmn-io layout process.bpmn           # automatic DI layout to stdout
```

## API

| Name | Module | Contract |
|---|---|---|
| `BpmnModdle` | `bpmn_io.bpmn_moddle` | default model (six descriptors), lax `from_xml`, `to_xml` |
| `create_moddle` | `bpmn_io.bpmn_moddle` | `BpmnModdle` plus additional descriptor packages |
| `check` / `Report` | `bpmn_io.check` | L0 integrity: warnings, unresolved references, unknown attributes |
| `layout_process` / `Layouter` | `bpmn_io.auto_layout` | automatic DI layout; `LayoutError` on failure |
| `is_a` | `bpmn_io.bpmn_moddle.types` | `TypeGuard` narrowing on descriptor literal types |
| `ParseResult` / `ParseError` | `bpmn_io.moddle_xml` | read result / failure |
| `SerializationResult` | `bpmn_io.bpmn_moddle` | `to_xml` result (`xml`, `warnings`) |
| `DESCRIPTOR_NAMES` / `load_descriptor` | `bpmn_io.descriptors` | vendored descriptor registry |
| `UPSTREAM_VERSIONS` | `bpmn_io.upstream` | pinned upstream versions |

## Development

```bash
uv sync                      # Python 3.11+, all dependency groups
uv run pytest                # Python test-suite
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/sync_upstream.py --check     # vendored upstream files untouched
uv run python scripts/port_coverage.py             # upstream test-suite port status
(cd tests/oracle && npm ci --ignore-scripts) && uv run pytest -m oracle   # Node differential tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the porting workflow and the release process.

## Upstream versions

| Upstream | Version |
|---|---|
| saxen | 11.2.0 |
| min-dash | 5.1.0 |
| moddle | 8.2.1 |
| moddle-xml | 12.3.1 |
| bpmn-moddle | 10.3.1 |
| bpmn-in-color-moddle | 0.2.0 |
| bpmn-auto-layout | 1.3.0 |
