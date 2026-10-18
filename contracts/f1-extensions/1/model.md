# F1 wire model and native mapping (contract f1-extensions/1)

Freezes the field-level mapping between the native tree of bpmn-moddle
10.3.1 / moddle-xml 12.3.1 and the JSON wire form validated by
`f1-wire.schema.json`. Key order on the wire is UTF-16 code-unit order
(see `profile-c14n/2`); attribute source order is excluded from
preservation.

## Generic elements (`$type: "$any"`)

Generic dispatch precedes every registered-type guard, in both
projection and hydration.

| Field | Contract and reconstruction |
| --- | --- |
| `$type` | The constant `"$any"`. It is not a registered type name. |
| `$name` | Required `{qname, uri}` of strings taken from the native generic name and namespace descriptor. Hydration derives prefix/local name from `qname` only, never from a preferred application prefix. |
| `$attrs` | Required string-to-string map; `{}` means no foreign attributes. Native generic attribute properties map into it and are restored on hydration. Retained `xmlns` and `xmlns:p` declarations stay ordinary entries here, exactly where the native tree retains them. There is no separate declarations array and no source declaration-position record. |
| `$body` | Optional string holding the native body. Presence is preserved, including an explicitly present empty string; absence stays absent. No trimming, coalescing or lexical reconstruction. |
| `$children` | Optional array preserving native presence and array order, including an explicitly empty array. |

Runtime links (`$parent`, model/descriptor objects, methods) are omitted
from JSON; hydration rebuilds parent links and typed-reference identity.
Generic ids and attribute values remain strings and never enter the
typed id/reference index.

## Registered (typed) elements

Typed elements keep their existing JSON shape: `$type` plus one entry
per set non-reference property under its descriptor name, in UTF-16
key order, plus the `$attrs` map. Reference properties project to
`{"$ref": "<id>"}` (arrays for many-valued references) so hydration
can rebuild typed-reference identity. `$attrs` holds foreign
attributes as a string-to-string map and is always present (`{}` when
empty); this matches the existing writer-visible convention and keeps
the `project(hydrate(J)) == J` fixed point exact. Unknown content is
not automatically invalid.

## Namespaces

Each prefixed name retains its namespace URI exactly as the native
tree records or resolves it: generic identity uses `$name.uri`;
attribute bindings use retained `$attrs` declarations, native scope
and descriptor metadata. A URI is never inferred from spelling alone.
Default namespaces apply to element names, never to unprefixed
attributes; native treatment of `xmlns=""` is preserved. The `xml`
prefix is fixed to `http://www.w3.org/XML/1998/namespace`; its
declaration is never generated.

No-namespace representation: an element or attribute in no namespace
carries the empty-string URI `""` in `$name.uri`. A missing `uri`
field is invalid; an empty `uri` with a prefixed `qname` is invalid.

Generic-descendant rule: every descendant handled generically by the
native reader remains generic in JSON, even when its QName uses a
registered namespace prefix. Hydration rebuilds such nodes with
`createAny` semantics and never reclassifies them as typed.

## Descriptors, xsi and slots

Generic nodes are valid in descriptor slots of type `Element`,
including `extensionElements.values`, and in generic `$children`. They
remain invalid in incompatible typed slots or as typed-reference
targets; hydration rejects cycles, shared children and inconsistent
parents with `descriptor-mismatch`.

Registered descriptor mismatches are typed incompatibilities, never a
reason to reclassify a known node as generic. Arbitrary foreign string
values are preserved without interpreting ids, expressions or schema
locations.

`xsi:type` follows native slot/type resolution, including legitimate
subtypes, aliases and default-namespace behaviour. Only metadata
actually retained by the native tree is preserved; unknown typed
discriminators follow native warning/refusal behaviour, never an
invented generic fallback. Other `xsi` attributes are treated exactly
as native attributes: no new nil/content rule, no schema-location
rewriting, no schema retrieval.

## Fixed points

- `project(hydrate(J)) == J` in the sealed JSON normal form (UTF-16
  key order, omission rules applied, explicit defaults expanded).
- `hydrate(project(M))` reconstructs the representable tree of `M`.
- Inputs are immutable: neither call mutates its input.
- Arbitrary JSON is not required to equal its first XML round trip:
  native writing/parsing can add a discriminator or declaration, or
  normalize a retained value. The first-pass native delta is frozen
  per vector (including the FormalExpression case); subsequent
  stabilization is proved where the native reference stabilizes.
- For identical native inputs and options, F7 matches the existing
  literal-writer bytes. XML to native to JSON to native to XML adds no
  loss beyond the native reader/writer.
