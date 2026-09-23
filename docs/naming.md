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

## min-dash (Lot 2 inventory)

Every min-dash import in the ported libraries, and its fate in `bpmn_io._min_dash`
(sources: `tests/upstream/min-dash/lib/*.js`, v5.1.0).

| Downstream file | Helpers used |
|---|---|
| `moddle/lib/types.js` | `assign` |
| `moddle/lib/factory.js` | `forEach`, `bind` |
| `moddle/lib/properties.js` | `assign`, `isString` |
| `moddle/lib/descriptor-builder.js` | `pick`, `assign`, `forEach`, `bind` |
| `moddle/lib/moddle.js` | `isString`, `isObject`, `forEach`, `set` |
| `moddle/lib/registry.js` | `assign`, `forEach`, `bind` |
| `moddle-xml/lib/read.js` | `forEach`, `find`, `assign` |
| `moddle-xml/lib/write.js` | `forEach`, `isString`, `filter`, `assign`, `has`, `findIndex` |
| `bpmn-moddle/lib/simple.js` | `assign` |
| `bpmn-moddle/lib/bpmn-moddle.js` | `isString`, `assign` |
| `bpmn-auto-layout/lib/di/DiFactory.js` | `assign`, `map`, `pick` |
| `bpmn-auto-layout/lib/Layouter.js` | `isFunction` |
| `saxen/lib/**` | (none) |

Transposed (13, camelCase → snake_case): `assign`, `bind`, `filter`, `find`,
`find_index`, `for_each`, `has`, `is_function`, `is_object`, `is_string`, `map`,
`pick`, `set`.

Not transposed (N-A, claimed with reason in `tests/min_dash/`): `flatten`, `without`,
`reduce`, `every`, `some`, `values`, `keys`, `groupBy`, `uniqueBy`, `unionBy`, `size`,
`sortBy`, `matchPattern`, `debounce`, `throttle`, `isDefined`, `isUndefined`, `isNil`,
`isArray`, `isNumber`, `ensureArray`, `get`, `omit`, `merge` — none is imported by the
libraries above; `debounce`/`throttle` additionally have no equivalent in the
synchronous port. Python `None` is JS `null` and `UNDEFINED` (`bpmn_io._js`) is JS
`undefined`, so `find` misses and `for_each` completions surface as `UNDEFINED`.
