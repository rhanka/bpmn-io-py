# bpmn-py

**bpmn.io's `bpmn-moddle` and `bpmn-auto-layout`, transposed to pure Python.**

Read, check, build, lay out and write BPMN 2.0 XML from Python, with the exact object model and
semantics of the reference JavaScript implementation, and no runtime dependency.

> Status: pre-alpha. The repository scaffold, upstream pins and conformance tooling are in place;
> the port itself is in progress. Nothing is published on PyPI yet.
>
> bpmn-py is an independent project, not affiliated with bpmn.io or Camunda.

## Why this exists

BPMN is a natural target for AI agents written in Python (Google ADK, LangGraph, plain SDK
agents, …): an agent can draft a process, check it, lay it out and hand a valid `.bpmn` file to a
human or to an engine. Until now the only faithful implementation of the BPMN 2.0 meta-model
(`bpmn-moddle`) and of automatic diagram layout (`bpmn-auto-layout`) lived in JavaScript, so a
Python agent had to shell out to Node or skip validation altogether.

bpmn-py removes that gap: a 100 % mapped Python port, so the objects, the warnings and the XML you
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

## Planned API (mirrors upstream)

```python
from bpmn_py import BpmnModdle

moddle = BpmnModdle()
result = moddle.from_xml(xml)  # ParseResult(root_element, references, warnings, elements_by_id)
definitions = result.root_element
task = moddle.create("bpmn:Task", name="Review")
xml_out = moddle.to_xml(definitions, format=True)

from bpmn_py import layout_process  # bpmn-auto-layout

laid_out = layout_process(xml_out)  # BPMN with generated DI
```

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
| bpmn-auto-layout | 1.3.0 |
