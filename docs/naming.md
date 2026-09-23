# JS → Python naming table (EVOL D3) and test idioms (EVOL D4.1)

## Identifiers

| JS | Python | Example |
|---|---|---|
| function, method, variable (camelCase) | snake_case | `fromXML` → `from_xml`, `getType` → `get_type` |
| class | PascalCase (unchanged) | `Moddle`, `BpmnModdle` |
| moddle *property* names | unchanged (they are the BPMN attribute names) | `element.get("sourceRef")` |
| constant | UPPER_SNAKE (unchanged) | — |

## `$` members (PEP 8 trailing underscore)

| JS | Python |
|---|---|
| `$type` | `element.type_` |
| `$attrs` | `element.attrs_` |
| `$parent` | `element.parent_` |
| `$descriptor` | `element.descriptor_` |
| `$model` | `element.model_` |
| `$instanceOf` | `element.instance_of(...)` |

`get("$type")` also works. Bare `type` is never used for `$type` because `type` is a real
BPMN property on four types (`Relationship`, `ExtensionAttributeDefinition`,
`CorrelationProperty`, `ResourceParameter`).

## Reserved and special names

- Python keywords among properties (`from`, `import`): reachable only through `get`/`set`,
  `create(..., **{"from": x})` and `getattr`; never as bare attributes. `Assignment.from` is
  serialized with `xsi:type`, so the keyword rule is exercised by the writer roundtrip too.
- Dynamic attribute access (`__getattr__`) never intercepts dunder names, so `copy`, `pickle`,
  `hasattr` and debugger introspection behave normally.

## Errors

| JS | Python |
|---|---|
| rejected promise on reader failure (with `err.warnings`) | raised `ParseError` carrying `.warnings` |
| rejected promise on layout failure | raised `LayoutError` |
| layout warning value | `LayoutWarning` (name kept) |

## Async → sync mapping (mechanical, counts as *ported*)

Upstream `await moddle.fromXML(xml)` → `moddle.from_xml(xml)`; a rejected promise → a raised
exception (table above).

## Test idioms (mechanical, counts as *ported*)

| JS (mocha/chai) | Python (pytest) |
|---|---|
| `await expect(p).to.be.rejectedWith(...)` | `with pytest.raises(ParseError) as info:` + same assertions on `info.value` |
| `try { await … } catch (err) { … }` | `with pytest.raises(...)` + same assertions |
| `expect(x).to.eql(y)` on models | `json_equal(x, y)` (`tests/_matchers.py`; `$parent`/`$model`/`$descriptor` excluded, insertion order kept) |
| `expect(x).to.eql(y)` on plain values | `==` |
| `expect(s).to.match(re)` | `re.search(...)` |
| `expect(s).to.contain(x)` | `in` |
| `expect(a).to.have.length(n)` | `len(...)` |
| `expect(x).to.be.true` / `.false` | `is True` / `is False` |
| `expect(x).to.exist` | `is not None` |
| dynamic cases (one per fixture / schema) | enumerated by the oracle ledger (`tests/upstream/LEDGER.json`) or expanded from fixture files |
