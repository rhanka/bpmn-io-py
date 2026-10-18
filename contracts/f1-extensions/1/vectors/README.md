# F1 vectors (`contracts/f1-extensions/1/vectors/`)

Each vector pins one contract behavior with inputs authored from the F1
text and expectations from the independent Node references
(`tests/oracle/f1_references.mjs` against bpmn-moddle 10.3.1 /
moddle-xml 12.3.1), reviewed before sealing. Python codec output never
authors a golden.

## File kinds per vector `<id>`

| Suffix | Provenance | Content |
| --- | --- | --- |
| `.input.xml` / `.input.json` / `.input.bin` | hand-authored | conversion input |
| `.wire.json` | Node `wire` op | expected projected JSON |
| `.f7.xml` | Node `serialize`/`genericSerialize` op | expected writer bytes |
| `.meta.json` | hand-authored | stage assertions (see below) |
| `.expect.txt` | canonical form | expected UTF-16-ordered bytes (c14n unit vectors) |

Absent files are meaningful: no `.f7.xml` means the native writer
throws (sealed limitation, both lanes) or the bytes are not UTF-8
(lone-surrogate trees, refused O1); no `.wire.json` means the vector
is JSON-input-only.

## `.meta.json` schema

`design` cites F1 plan revision d clauses. `parse` / `hydrate` pin
`ok` plus the expected `(code, path, target)` diagnostic tuples in
order (details stay unpinned). `project` pins loss diagnostics.
`serialize.ok: false` pins O1/limit/native-writer refusals; a `native`
note records where the literal writer throws identically in both
lanes. `kind: "c14n"` marks canonical-form unit vectors.
