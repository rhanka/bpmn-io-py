# Third-party notices

bpmn-io is a literal transposition to Python of the following bpmn.io libraries. Their algorithms,
descriptors, test fixtures and test-suites are reproduced or translated here under the terms of the
MIT License, with the original copyright notice preserved. bpmn-io is an independent project and is
**not affiliated with, endorsed by, or supported by bpmn.io or Camunda**.

| Upstream project | Version | Copyright | License | What is transposed |
|---|---|---|---|---|
| [saxen](https://github.com/nikku/saxen) | 11.2.0 | 2012 Vopilovskii Konstantin; 2017-present Nico Rehwaldt | MIT | lenient SAX XML parser, test-suite |
| [min-dash](https://github.com/bpmn-io/min-dash) | 5.1.0 | 2017-present camunda Services GmbH | MIT | the utility helpers used by the libraries below, their tests |
| [moddle](https://github.com/bpmn-io/moddle) | 8.2.1 | 2014-present Camunda Services GmbH | MIT | meta-model runtime (registry, factory, properties), moddle.json schema, test-suite |
| [moddle-xml](https://github.com/bpmn-io/moddle-xml) | 12.3.1 | 2014-present Camunda Services GmbH | MIT | XML reader/writer, test-suite and fixtures |
| [bpmn-moddle](https://github.com/bpmn-io/bpmn-moddle) | 10.3.1 | 2014 camunda Services GmbH | MIT | BPMN 2.0 / DI / DC / bioc descriptors (`src/bpmn_io/resources`), wiring, test-suite and fixtures |
| [bpmn-auto-layout](https://github.com/bpmn-io/bpmn-auto-layout) | 1.3.0 | bpmn.io contributors (package.json declares MIT; no LICENSE file at the pinned tag, status unverified) | MIT | layout algorithm, test-suite, fixtures and snapshots |

Exact tags, commits and per-file sha256 digests of every vendored file are recorded in
`UPSTREAM.toml` and `UPSTREAM.lock`.

The BPMN 2.0 descriptors were generated upstream from the OMG BPMN 2.0 specification metamodel
(CMOF). The OMG XSD schema files are **not** redistributed by this package.

## Upstream license text

The same MIT text applies to every project above, with the copyright holder(s) listed in the table.

```
The MIT License (MIT)

Copyright (c) <holder(s) as listed above>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```
