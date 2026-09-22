# Security policy

Supported: the latest released minor version.

Report vulnerabilities privately through GitHub Security Advisories on this repository
("Report a vulnerability"). Please do not open public issues for security reports.

XML handling: bpmn-py parses with a pure-Python transposition of `saxen`, which ignores DTDs,
never resolves external entities, and expands only the XML built-in and numeric character
references.
