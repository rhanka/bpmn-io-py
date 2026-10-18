# `bpmn_io.codec`: generic extension-preserving codec (F1 lane)

Published Python lane of the F1 plan (revision d). The codec projects the
native tree of bpmn-moddle 10.3.1 / moddle-xml 12.3.1 to JSON and back
without losing unregistered extensions, and serializes back to XML (F7)
through the unchanged literal writer. Contract: `contracts/f1-extensions/1/`
(this repository is its canonical owner). Vectors:
`contracts/f1-extensions/1/vectors/`. Python receipt:
`contracts/f1-extensions/1/receipt-py.json`.

## Public API

```python
from bpmn_io.codec import parse_xml, project, hydrate, serialize_xml

parsed = parse_xml(source, descriptors=None, limits=None)  # bytes|str -> native root
projected = project(root, descriptors=None, limits=None)  # native root -> JSON dict
rehydrated = hydrate(data, descriptors=None, limits=None)  # JSON dict -> native root
out = serialize_xml(root, format=False, preamble=True)  # native root -> str
```

Every call returns a frozen `CodecResult(ok, value, diagnostics)`.
`Diagnostic` carries `(code, path, target, detail)`: `path` is an
RFC 6901 pointer (or `None` for element-less native failures, whose
native line/column ships in `detail`); `target` is an id (or `None`).
Diagnostics are ordered deterministically: scan observations in input
order, then native warnings in collection order, with UTF-16 key order
inside one node.

`descriptors` injects extra moddle packages (a dict; a valid empty map
is accepted and behaves like the default model). Descriptors validate
once per conversion; each call builds its own model, so calls share
nothing. `limits` optionally tightens the frozen limit table.

## Wire model

Registered elements project to `$type` plus one entry per set
non-reference property, with references as `{"$ref": id}` and foreign
attributes in an always-present `$attrs` map. Generic elements dispatch
first on `$type: "$any"` with `$name {qname, uri}`, a required
`$attrs` string map (retained `xmlns` declarations stay ordinary
entries), optional `$body` and optional `$children`. Parents and
typed-reference identity rebuild on hydration; generic ids never enter
the typed index. Unprefixed names in no namespace carry the
empty-string URI; descendants the native reader handles generically
stay generic even under registered prefixes.

Fixed points: `project(hydrate(J)) == J`; `hydrate(project(M))`
rebuilds the representable tree. After an F7 pass, explicit
descriptor defaults the literal writer drops are gone and the second
pass is stable (pinned by the MIWG tests).

## Boundary behavior

`parse_xml` enforces, before native construction: the input-encoding
registry (UTF-8 default, strict; ISO-8859-1 family with the true
byte-to-`U+0000..U+00FF` mapping; anything else refuses), raw and
decoded size checks, `DOCTYPE`/`ENTITY` refusal, reserved-name,
duplicate, malformed-name, unbound-prefix and entity-reference checks,
then limit counting through the pinned tokenizer events. Native
warnings and losses map to the closed 26-code diagnostic enum
(`contracts/f1-extensions/1/diagnostics.json`), capped at 1000 plus
one `moddle-warning-truncated`. Comments, processing instructions,
CDATA boundaries and truncating numeric references surface as typed
loss diagnostics with `f1-xml-source/1` coordinates.

`serialize_xml` validates every string before encoding (O1: lone
surrogates, NUL, C0 controls except TAB/LF/CR, DEL, C1 controls and
`U+FFFE`/`U+FFFF` refuse) and emits complete diagnostic tuples (O2).
F7 bytes equal the literal-writer oracle for every encodable tree.

## Known native limitations (identical in both lanes)

- Locally rebound or default-reset generic prefixes are anonymized by
  the native reader (`ns0` with an empty URI); such trees project but
  neither hydrate nor serialize (pinned vectors `prefix-collision-01`,
  `prefix-defaultreset-01`).
- Past 1000 native warnings the adapter points the shared
  `moddle-warning-truncated` diagnostic at the first omitted warning,
  observed by wrapping the warning sink the literal reader exposes
  (the reader port itself is unmodified; sealed vector
  `warning-cap-01`).
- The literal Python port skips escaping a lone `'` where the Node
  writer emits `&#39;` (sealed strict-xfail; the Node oracle stays
  authoritative).
