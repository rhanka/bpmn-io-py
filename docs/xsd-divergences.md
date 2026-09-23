# XSD validation divergences: Xerces vs lxml (Lot 7)

Upstream `validate(xml)` is `xsd-schema-validator` (Java/Xerces) against
`test/fixtures/xsd/BPMN20.xsd`. The Python port validates through
`lxml.etree.XMLSchema` against the same `BPMN20.xsd`, with its dangling
`schemaLocation` entries rewritten to absolute file URIs at test setup:

- `../../../resources/bpmn/xsd/BPMNDI.xsd` and
  `../../../resources/bpmn/xsd/Semantic.xsd` (which do not exist next to the
  fixtures) point at the OMG XSDs shipped inside the vendored `bpmn-moddle`
  npm package (`tests/oracle/node_modules/bpmn-moddle/resources/bpmn/xsd/`);
- `Vendor.xsd` points at the fixture copy next to `BPMN20.xsd`.

No network resolution is used. Both validation points are kept: input
pre-validation (`fromValidFile` equivalents) and post-serialization
`validate(xml)` — 45 sites across `xml/test_roundtrip.py` (42),
`xml/test_edit.py` (2) and `integration/test_camunda.py` (1).

## Observed divergences

None. All 45 `validate(xml)` sites pass under both validators with the
current fixtures: every roundtrip/edit/camunda input fixture validates, and
every serialization validates. The ported suite is green under
`lxml 6.1.3` with byte-identical output on the three byte-exact cases
(`namespace-redefinition`, `operation-ref-message-event-definition`,
`operation-ref-as-attribute`).

## Known risk areas (no divergence observed; record here if one appears)

- `windows-1252` bad-encoding fixture: a read-warning case
  (`unsupported document encoding <windows-1252>`), never a validate case.
- Vendor extensions (`vendor:*`, `bioc:*`, `camunda:*`, `drools:*`,
  `i18n:*`, `myNs:*`): accepted lax via `xsd:anyAttribute processContents="lax"`
  and `Vendor.xsd`; Xerces and libxml2 agree on all fixtures using them.
- `xml:lang` attributes and `xsi:type` specializations (`bpmn:tFormalExpression`,
  `expr:Guard`): validated clean on `xml-lang.bpmn`, `xsi-type.bpmn`,
  `expression-plain.bpmn` (which asserts the default `xsi:type` is omitted).
- `obscure ids` (`foo_bar`, `foo-bar`, `_11`, …): `xsd:ID`-valid on both sides.

## Reproducing

```bash
.venv/bin/python -m pytest tests/bpmn_moddle/xml/test_roundtrip.py \
  tests/bpmn_moddle/xml/test_edit.py tests/bpmn_moddle/integration -q
```
