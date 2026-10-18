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
| [bpmn-in-color-moddle](https://github.com/bpmn-io/bpmn-in-color-moddle) | 0.2.0 | bpmn.io contributors | MIT | BPMN in Color descriptor (`src/bpmn_io/resources/color`) |
| [bpmn-auto-layout](https://github.com/bpmn-io/bpmn-auto-layout) | 1.3.0 | bpmn.io contributors (package.json declares MIT; no LICENSE file at the pinned tag, status unverified) | MIT | layout algorithm, test-suite, fixtures and snapshots |
| [bpmnlint](https://github.com/bpmn-io/bpmnlint) | 11.15.0 | 2018-present bpmn.io Contributors | MIT | linter core, 29 built-in rules, configs, test-suite and fixtures |
| [bpmnlint-utils](https://github.com/bpmn-io/bpmnlint-utils) | 1.1.1 | 2018-present bpmn.io Contributors | MIT | rule-authoring utilities (`is`, `isAny`, checks), test-suite |
| [@bpmn-io/moddle-utils](https://github.com/bpmn-io/moddle-utils) | 0.3.0 | 2022-present Camunda Services GmbH | MIT | moddle element path/id utilities, test-suite |

Exact tags, commits and per-file sha256 digests of every vendored file are recorded in
`UPSTREAM.toml` and `UPSTREAM.lock`.

## Unicode Character Database 15.0.0 (case tables)

The pinned full default case data in `src/bpmn_io/profile/_unicode15.py` is
derived from the Unicode Character Database 15.0.0 (`UnicodeData.txt`,
`SpecialCasing.txt`, `DerivedCoreProperties.txt`; source names, sizes and
SHA-256 recorded in `contracts/unicode-case/15.0.0/manifest.json` and in the
generated module header). The raw UCD files are not vendored. The derivation
is reproduced by `scripts/gen_unicode_case.py` (`--check` re-derives from the
hash-verified sources). Copyright © 1991-2026 Unicode, Inc. Distributed under
the UNICODE LICENSE V3, reproduced below.

```
UNICODE LICENSE V3

COPYRIGHT AND PERMISSION NOTICE

Copyright © 1991-2026 Unicode, Inc.

NOTICE TO USER: Carefully read the following legal agreement. BY
DOWNLOADING, INSTALLING, COPYING OR OTHERWISE USING DATA FILES, AND/OR
SOFTWARE, YOU UNEQUIVOCALLY ACCEPT, AND AGREE TO BE BOUND BY, ALL OF THE
TERMS AND CONDITIONS OF THIS AGREEMENT. IF YOU DO NOT AGREE, DO NOT
DOWNLOAD, INSTALL, COPY, DISTRIBUTE OR USE THE DATA FILES OR SOFTWARE.

Permission is hereby granted, free of charge, to any person obtaining a
copy of data files and any associated documentation (the "Data Files") or
software and any associated documentation (the "Software") to deal in the
Data Files or Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, and/or sell
copies of the Data Files or Software, and to permit persons to whom the
Data Files or Software are furnished to do so, provided that either (a)
this copyright and permission notice appear with all copies of the Data
Files or Software, or (b) this copyright and permission notice appear in
associated Documentation.

THE DATA FILES AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF
THIRD PARTY RIGHTS.

IN NO EVENT SHALL THE COPYRIGHT HOLDER OR HOLDERS INCLUDED IN THIS NOTICE
BE LIABLE FOR ANY CLAIM, OR ANY SPECIAL INDIRECT OR CONSEQUENTIAL DAMAGES,
OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THE DATA
FILES OR SOFTWARE.

Except as contained in this notice, the name of a copyright holder shall
not be used in advertising or otherwise to promote the sale, use or other
dealings in these Data Files or Software without prior written
authorization of the copyright holder.
```

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
