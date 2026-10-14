"""Ported tests for ``compile_config`` (upstream ``test/spec/support/compile-config-spec.mjs``)."""

from __future__ import annotations

import pytest

from bpmn_io.lint.resolver.node_resolver import NodeResolver
from bpmn_io.lint.support.compile_config import compile_config


class _MockRequire:
    def __init__(self, require_fn: object, resolve_fn: object = None) -> None:
        self._require_fn = require_fn
        self._resolve_fn = resolve_fn

    def __call__(self, path: str) -> object:
        return self._require_fn(path)

    def resolve(self, path: str) -> str:
        if self._resolve_fn is None:
            msg = f"not found: {path}"
            raise ModuleNotFoundError(msg)
        return self._resolve_fn(path)


def _not_found(path: str) -> object:
    msg = f"not found: {path}"
    raise ModuleNotFoundError(msg)


@pytest.mark.upstream(
    "bpmnlint/test/spec/support/compile-config-spec.mjs",
    "support/compile-config > should import rules",
)
def test_compile_import_rules() -> None:
    code = compile_config(
        {
            "rules": {
                "conditional-flows": "error",
                "single-blank-start-event": "off",
                "end-event-required": "info",
                "no-bpmndi": 1,
                "no-implicit-split": "warn",
            },
        },
    )

    assert "import rule_0 from 'bpmnlint/rules/conditional-flows'" in code
    assert "cache['bpmnlint/conditional-flows'] = rule_0" in code
    assert "import rule_2 from 'bpmnlint/rules/end-event-required'" in code
    assert "cache['bpmnlint/end-event-required'] = rule_2" in code
    assert "import rule_3 from 'bpmnlint/rules/no-bpmndi'" in code
    assert "cache['bpmnlint/no-bpmndi'] = rule_3" in code
    assert "import rule_4 from 'bpmnlint/rules/no-implicit-split'" in code
    assert "cache['bpmnlint/no-implicit-split'] = rule_4" in code

    assert "cache['bpmnlint/single-blank-start-event']" not in code
    assert "bpmnlint/rules/single-blank-start-event" not in code

    assert '"conditional-flows": "error"' in code
    assert '"single-blank-start-event": 0' in code
    assert '"end-event-required": "info"' in code
    assert '"no-bpmndi": 1' in code
    assert '"no-implicit-split": "warn"' in code

    assert "export { resolver, config, moddleExtensions };" in code
    assert "export default bundle;" in code


@pytest.mark.upstream(
    "bpmnlint/test/spec/support/compile-config-spec.mjs",
    "support/compile-config > should import moddle extensions",
)
def test_compile_import_moddle_extensions() -> None:
    code = compile_config(
        {
            "moddleExtensions": {
                "abs": "abs-moddle/resources/abs.json",
                "rel": "./relative-moddle.json",
            },
        },
    )

    assert "import moddle_extension_0 from 'abs-moddle/resources/abs.json'" in code
    assert "moddleExtensions['abs'] = moddle_extension_0;" in code
    assert "import moddle_extension_1 from './relative-moddle.json'" in code
    assert "moddleExtensions['rel'] = moddle_extension_1;" in code
    assert "export { resolver, config, moddleExtensions };" in code
    assert "export default bundle;" in code


@pytest.mark.upstream(
    "bpmnlint/test/spec/support/compile-config-spec.mjs",
    "support/compile-config > should import namespaced",
)
def test_compile_import_namespaced() -> None:
    code = compile_config({"rules": {"@foo/bar/rule": "warn"}})

    assert "import rule_0 from '@foo/bpmnlint-plugin-bar/rules/rule'" in code
    assert "cache['@foo/bpmnlint-plugin-bar/rule'] = rule_0" in code


@pytest.mark.upstream(
    "bpmnlint/test/spec/support/compile-config-spec.mjs",
    "support/compile-config > should import custom path rules > through external source",
)
def test_compile_custom_path_external() -> None:
    def __require(path: str) -> object:
        if path == "bpmnlint-plugin-foreign":
            return {
                "configs": {
                    "recommended": {
                        "rules": {
                            "exported-path": "error",
                            "exported-external-path": "some-rule-library",
                        },
                    },
                },
                "rules": {
                    "exported-path": "./rules/exported-path",
                    "exported-external-path": "some-rule-library",
                },
            }
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    def __resolve(path: str) -> str:
        if path == "bpmnlint-plugin-foreign/package.json":
            return "/bpmnlint-plugin-foreign/package.json"
        if path == "bpmnlint-plugin-foreign":
            return "/bpmnlint-plugin-foreign/lib/index.js"
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    resolver = NodeResolver(require=_MockRequire(__require, __resolve))
    code = compile_config({"extends": "plugin:foreign/recommended"}, resolver)

    assert "import rule_0 from 'bpmnlint-plugin-foreign/lib/rules/exported-path'" in code
    assert "cache['bpmnlint-plugin-foreign/exported-path'] = rule_0" in code
    assert "import rule_1 from 'some-rule-library'" in code
    assert "cache['bpmnlint-plugin-foreign/exported-external-path'] = rule_1" in code


@pytest.mark.upstream(
    "bpmnlint/test/spec/support/compile-config-spec.mjs",
    "support/compile-config > should import custom path rules > through local source",
)
def test_compile_custom_path_local() -> None:
    def __require(path: str) -> object:
        if path == "./package.json":
            return {"name": "bpmnlint-plugin-local"}
        if path == ".":
            return {
                "configs": {
                    "recommended": {
                        "rules": {
                            "exported-path": "error",
                            "exported-external-path": "some-rule-library",
                        },
                    },
                },
                "rules": {
                    "exported-path": "./rules/exported-path",
                    "exported-external-path": "some-rule-library",
                },
            }
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    def __resolve(path: str) -> str:
        if path == "./package.json":
            return "bpmnlint-plugin-local/package.json"
        if path == ".":
            return "bpmnlint-plugin-local/lib/index.js"
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    resolver = NodeResolver(require=_MockRequire(__require, __resolve))
    code = compile_config({"extends": "plugin:local/recommended"}, resolver)

    assert "import rule_0 from 'bpmnlint-plugin-local/lib/rules/exported-path'" in code
    assert "cache['bpmnlint-plugin-local/exported-path'] = rule_0" in code
    assert "import rule_1 from 'some-rule-library'" in code
    assert "cache['bpmnlint-plugin-local/exported-external-path'] = rule_1" in code


@pytest.mark.upstream(
    "bpmnlint/test/spec/support/compile-config-spec.mjs",
    "support/compile-config > should import custom path rules > handling illegal path errors",
)
def test_compile_illegal_path_errors() -> None:
    def __require(path: str) -> object:
        if path == "./package.json":
            return {"name": "bpmnlint-plugin-local"}
        if path == ".":
            return {
                "configs": {
                    "recommended": {
                        "rules": {"not-a-path": "error"},
                    },
                },
                "rules": {"not-a-path": dict},
            }
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    resolver = NodeResolver(require=_MockRequire(__require))
    with pytest.raises(
        ValueError,
        match="failed to bundle rule <not-a-path> from <.>: illegal rule export",  # noqa: RUF043
    ):
        compile_config({"extends": "plugin:local/recommended"}, resolver)


@pytest.mark.upstream(
    "bpmnlint/test/spec/support/compile-config-spec.mjs",
    "support/compile-config > should resolve extends",
)
def test_compile_resolve_extends() -> None:
    code = compile_config({"extends": "bpmnlint:recommended"})

    assert "conditional-flows" in code
    assert "single-blank-start-event" in code


@pytest.mark.upstream(
    "bpmnlint/test/spec/support/compile-config-spec.mjs",
    "support/compile-config > error handling > should throw on illegal moddle extensions",
)
def test_compile_illegal_moddle_extensions() -> None:
    with pytest.raises(
        TypeError,
        match="illegal value for moddle-extension abs: expected <string>",
    ):
        compile_config({"moddleExtensions": {"abs": {"test": "nested object"}}})
