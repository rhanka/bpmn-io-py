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

## saxen (Lot 3 inventory)

`saxen` is consumed by exactly one downstream library: `moddle-xml/lib/read.js`
imports `{ Parser as SaxParser }`, builds `new SaxParser({ proxy: true })`,
calls `.ns(uriMap)`, and decodes text via the `decodeEntities` handler argument.
The port exposes the same surface from `bpmn_io.saxen` (sources:
`tests/upstream/saxen/lib/*.js`, v11.2.0 pinned in `tests/oracle/package.json`).

| Upstream name | Port name | Notes |
|---|---|---|
| `Parser` | `Parser` | `on`, `ns`, `parse`, `write` (chainable), `end`, `stop` |
| `decode` (decodeEntities) | `decode_entities` | handler arg + `ns` URI mapping use it |
| `Error` parse failures | `ParseError` | via `onError`, `parse`/`end` return, or default rethrow |
| handler `getContext` | bound `ctx()` | `{data, line, column}` |
| JS call tolerance (extras dropped, missing `undefined`) | `_adapt_arity` | missing parameters arrive as `None` |
| JS `String.prototype.trim` (strips U+FEFF) | `_js_trim` | root-level blank checks only |

Not transposed (N-A): nothing — the whole `lib/` surface is ported. `test/perf`
is N-A (benchmark harness, no assertions; noted in `tests/saxen/test_stream.py`).
`None` is JS `null`; there is no `undefined` in the saxen surface.

## moddle (Lot 4 inventory)

Downstream `moddle-xml/lib/read.js` uses `Moddle`, `parseNameNS`, `coerceType`,
`isSimpleType`; `moddle-xml/lib/write.js` uses `isSimpleType`, `parseNameNS`;
`bpmn-moddle/lib/bpmn-moddle.js` subclasses `Moddle`. The port exposes the exact
`lib/index.js` surface from `bpmn_io.moddle` (sources:
`tests/upstream/moddle/lib/*.js`, pinned in `tests/oracle/package.json`).

| Upstream name | Port name | Notes |
|---|---|---|
| `Moddle` (default) | `Moddle` | `create`, `create_any`, `get_type`, `get_element_descriptor`, `get_property_descriptor`, `get_type_descriptor`, `has_type` |
| `parseNameNS` | `parse_name_ns` | |
| `coerceType` | `coerce_type` | |
| `isBuiltInType` | `is_built_in_type` | |
| `isSimpleType` | `is_simple_type` | |
| `Base` element (`get`/`set`, `$type`/`$attrs`/`$parent`/`$descriptor`/`$model`/`$instanceOf`) | `AnyModdleElement` + `ModdleElement` | `__getattr__` never intercepts dunders; keyword-named properties via `get`/`set` |
| internal `DescriptorBuilder`/`Registry`/`Factory`/`Properties` | same module split | `ns`/`types`/`properties`/`base`/`descriptor_builder`/`registry`/`factory`/`moddle` |
| `undefined` default / missing config | `UNDEFINED` (`bpmn_io._js`) | only `UNDEFINED` means "no default"; `None`/`False`/`0` are real defaults |

Not transposed (N-A): nothing public — internals keep the same split.
`moddle/test/integration/distro.*` are packaging checks, not ported as tests.

## moddle-xml Reader (Lot 5 inventory)

Downstream `bpmn-moddle/lib/bpmn-moddle.js` builds
`new Reader(assign({ model: this, lax: true }, options))` and calls
`fromXML(xmlStr, rootHandler)` (`rootHandler` from `handler(typeName)`).
The port exposes the same surface from `bpmn_io.moddle_xml` (sources:
`tests/upstream/moddle-xml/lib/read.js` → `read.py`, `common.js` →
`common.py`, pinned in `tests/oracle/package.json`).

| Upstream name | Port name | Notes |
|---|---|---|
| `Reader` | `Reader` | `Reader(model, lax=...)`, `handler(name)`, sync `from_xml(xml, root_handler)` |
| `fromXML` result `{rootElement, elementsById, references, warnings}` | `ParseResult` dataclass | `snake_case` keys; sync return / raise instead of Promise |
| `ParseError` (+ `.warnings`) | `ParseError` (+ `.warnings`) | strict failures raise; lax degrades to warnings |
| `lax: true` (BpmnModdle default) | `lax=True` | `unparsable content` becomes a warning + `NoopHandler` |
| `undefined` body / unset single ref | `UNDEFINED` (`bpmn_io._js`) | missing body is `UNDEFINED` (not `None`); unresolved single refs unset |
| `getContext` | bound `ctx()` | `{data, line, column}` |

Not transposed (N-A): the Writer (`write.js`, Lot 6). `test/perf` absent upstream
for moddle-xml.

## moddle-xml Writer (Lot 6 inventory)

Downstream `bpmn-moddle/lib/bpmn-moddle.js` builds `new Writer(options)` and
calls `toXML(element)` (Promise of `{xml}`); the port exposes `Writer`,
`WriteResult`, module-level `to_xml` from `bpmn_io.moddle_xml` (sources:
`tests/upstream/moddle-xml/lib/write.js` → `write.py`).

| Upstream name | Port name | Notes |
|---|---|---|
| `Writer` (`format`, `preamble` options) | `Writer` | `Writer(format=..., preamble=...)`, sync `to_xml(tree)` → `str` |
| `writer.toXML(element)` | `Writer.to_xml(tree, writer=None)` | string return, or streams into an `XmlSink` |
| `SavingWriter` / `FormatingWriter` (typo) | same + `FormattingWriter` alias | correct-spelling alias is additive |
| `toXML` Promise `{xml}` | module `to_xml` → `WriteResult` | sync; failures raise instead of rejecting |

Not transposed (N-A): `moddle-xml/test/integration/distro.cjs` (packaging
check, same as the moddle one). `performance.js` ported at full depth with no
timeout adaptation (runs within default limits).

## bpmn-moddle (Lot 7 inventory)

`BpmnModdle` wires six default descriptor packages (bpmn, bpmndi, dc, di,
bioc, color — the sixth vendored from `bpmn-in-color-moddle` 0.2.0, see
`UPSTREAM.toml`). Sources: `tests/upstream/bpmn-moddle/lib/*.js`.

| Upstream name | Port name | Notes |
|---|---|---|
| `BpmnModdle` (default, lax `fromXML`) | `BpmnModdle` | `Reader({"model", "lax": True})`; `from_xml`/`to_xml` delegates |
| `createModdle` (simple.js) | `create_moddle` | six default packages + additional ones |
| `toXML` Promise `{xml}` | `to_xml` → `SerializationResult` | sync; `options` `{format, preamble}` |
| L0 `check(xml | element)` | `check` → `Report` in `src/bpmn_io/check.py` | warnings, unresolved references, unknown attributes |

Not transposed (N-A): `bpmn-moddle/test/integration/distro.cjs` (packaging
check). `validate(xml)` cases run through `lxml` against the OMG XSDs;
divergences (none observed: 0 divergences, 45 validate sites) live in
`docs/xsd-divergences.md`.

## bpmn-auto-layout (Lot 8 inventory)

`layoutProcess(xml)` lays out the first root process of a DI-less document
and returns fresh-DI XML. Sources: `tests/upstream/bpmn-auto-layout/lib/**`
(9 files), pinned in `tests/oracle/package.json` (1.3.0). Port lives in
`src/bpmn_io/auto_layout/` with the same file split (snake_case).

| Upstream name | Port name | Notes |
|---|---|---|
| `layoutProcess(xml)` (index.js) | `layout_process` | module-level; sync (the JS `async` is incidental) |
| `Layouter` | `Layouter` | owns `BpmnModdle()` + `DiFactory`; `layout_process`, `handle` |
| rejected promise on layout failure | raised `LayoutError` | E1–E3 messages byte-identical; parse failures propagate `ParseError` unwrapped |
| layout warning value | `LayoutWarning` | defined, never raised (no upstream raise site in 1.3.0) |
| `Grid` | `Grid` | `find` → `(row, col)` tuple; `getGridDimensions` → `(rows, cols)`; identity (`is`) dedup |
| `DiFactory` | `DiFactory` | `create`, `create_di_bounds`, `create_di_label`, `create_di_shape`, `create_di_waypoints`, `create_di_edge`, `create_di_plane`, `create_di_diagram` |
| `getDefaultSize`, `is` (DiUtil) | `get_default_size`, `is_` | `is` is a keyword; same 9-branch size cascade |
| handler registry (handler/index.js) | `HANDLERS` | order significant: element, incoming, outgoing, attacher |
| `createElementDi`, `addToGrid`, `createConnectionDi` | `create_element_di`, `add_to_grid`, `create_connection_di` | attacher `add_to_grid` mutates the live `outgoing` list in place, as upstream |
| `isConnection`, `isBoundaryEvent`, `findElementInTree` | `is_connection`, `is_boundary_event`, `find_element_in_tree` | fresh `visited` set per top-level call |
| `getMid`, `getDockingPoint`, `connectElements`, `coordinatesToPosition`, `getBounds` | `get_mid`, `get_docking_point`, `connect_elements`, `coordinates_to_position`, `get_bounds` | |
| `DEFAULT_CELL_WIDTH`/`DEFAULT_CELL_HEIGHT` (layoutUtil) | same | 150/140; task size 100×80 lives in `di_util` |
| `Math.round` (boundary placement only) | `_js.math_round` | the only rounding site; all other geometry stays full-double |
| `Math.sign` | `_math_sign` private | inline; no shared-helper change |
| `undefined` reduce accumulator | `UNDEFINED` (`bpmn_io._js`) | falsy checks cover `0` and `UNDEFINED` |
| dynamic `gridPosition`/`grid`/`di`/`level`/`isExpanded` attrs | `grid_position`/same | read/written on moddle elements via `get`/plain-attr |

Not transposed (N-A): `UPDATE_SNAPSHOTS` regeneration and the browser
`output/index.html` report harness in `test/LayoutSpec.js` (harness-only, no
assertions). `example.bpmn` color-namespace stripping falls out of `clean_di`
+ writer behavior, not special-casing.
