"""Ported resolver tests (upstream ``test/spec/resolver/*-spec.mjs``).

The node-resolver cases are adapted to the Python resolver: the injectable
``require`` callables keep the upstream mock shapes (dicts stand in for
module exports, ``require.resolve`` returns node-style paths).
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.resolver.node_resolver import NodeResolver
from bpmn_io.lint.resolver.static_resolver import StaticResolver


class _MockRequire:
    """Callable with a ``resolve`` attribute, mirroring the upstream mocks."""

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


def _rule_resolver() -> NodeResolver:  # noqa: C901
    def __require(path: str) -> object:  # noqa: PLR0911
        if path == "./package.json":
            return {"name": "bpmnlint-plugin-local"}
        if path == ".":
            return {
                "rules": {
                    "exported-invalid": dict,
                    "exported-path": "./rules/exported-path",
                    "exported-external-path": "some-external-library",
                },
            }
        if path == "ROOT/bpmnlint-plugin-local/lib/rules/exported-path":
            return {"path": path}
        if path == "./rules/non-exported":
            return {"path": path}
        if path == "some-external-library":
            return {"path": path}
        if path == "bpmnlint-plugin-foreign":
            return {
                "rules": {
                    "exported-invalid": dict,
                    "exported-path": "./rules/exported-path",
                    "exported-external-path": "some-external-library",
                },
            }
        if path == "bpmnlint-plugin-foreign/lib/rules/exported-path":
            return {"path": path}
        if path == "bpmnlint-plugin-foreign/rules/non-exported":
            return {"path": path}
        if path == "ROOT/bpmnlint-plugin-foreign/lib/rules/exported-path":
            return {"path": path}
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    def __resolve(path: str) -> str:
        if path == ".":
            return "ROOT/bpmnlint-plugin-local/lib/index.js"
        if path == "bpmnlint-plugin-foreign":
            return "ROOT/bpmnlint-plugin-foreign/lib/index.js"
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    def __require_local(path: str) -> object:
        if path == "../../rules/label-required":
            return {"path": path}
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    return NodeResolver(
        require=_MockRequire(__require, __resolve),
        require_local=_MockRequire(__require_local, _not_found),
    )


@pytest.fixture
def rule_resolver() -> NodeResolver:
    return _rule_resolver()


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > built-in > should resolve",
)
def test_resolve_rule_builtin(rule_resolver: NodeResolver) -> None:
    assert rule_resolver.resolve_rule("bpmnlint", "label-required") == {
        "path": "../../rules/label-required",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > built-in > should fail to resolve",
)
def test_resolve_rule_builtin_fail(rule_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve rule <non-existing> from <bpmnlint>",
    ):
        rule_resolver.resolve_rule("bpmnlint", "non-existing")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - foreign > should resolve > via custom path (exported through $PKG.rules[$NAME]) > relative resolution",  # noqa: E501
)
def test_resolve_rule_foreign_relative(rule_resolver: NodeResolver) -> None:
    assert rule_resolver.resolve_rule("bpmnlint-plugin-foreign", "exported-path") == {
        "path": "ROOT/bpmnlint-plugin-foreign/lib/rules/exported-path",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - foreign > should resolve > via custom path (exported through $PKG.rules[$NAME]) > absolute resolution",  # noqa: E501
)
def test_resolve_rule_foreign_absolute(rule_resolver: NodeResolver) -> None:
    assert rule_resolver.resolve_rule("bpmnlint-plugin-foreign", "exported-external-path") == {
        "path": "some-external-library",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - foreign > should resolve > via default location ($PKG/rules/$NAME)",  # noqa: E501
)
def test_resolve_rule_foreign_default(rule_resolver: NodeResolver) -> None:
    assert rule_resolver.resolve_rule("bpmnlint-plugin-foreign", "non-exported") == {
        "path": "bpmnlint-plugin-foreign/rules/non-exported",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - foreign > should fail to resolve > handling non-existing rule",  # noqa: E501
)
def test_resolve_rule_foreign_missing_rule(rule_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve rule <non-existing> from <bpmnlint-plugin-foreign>",
    ):
        rule_resolver.resolve_rule("bpmnlint-plugin-foreign", "non-existing")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - foreign > should fail to resolve > handling non-existing plugin",  # noqa: E501
)
def test_resolve_rule_foreign_missing_plugin(rule_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve rule <exported> from <bpmnlint-plugin-non-existing>",
    ):
        rule_resolver.resolve_rule("bpmnlint-plugin-non-existing", "exported")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - foreign > should fail to resolve > handling illegal $PKG.rules[$NAME] export",  # noqa: E501
)
def test_resolve_rule_foreign_illegal(rule_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve rule <exported-invalid> from <bpmnlint-plugin-foreign>: illegal rule export",  # noqa: E501
    ):
        rule_resolver.resolve_rule("bpmnlint-plugin-foreign", "exported-invalid")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - local > should resolve > via custom path (exported through $PKG.rules[$NAME]) > relative resolution",  # noqa: E501
)
def test_resolve_rule_local_relative(rule_resolver: NodeResolver) -> None:
    assert rule_resolver.resolve_rule("bpmnlint-plugin-local", "exported-path") == {
        "path": "ROOT/bpmnlint-plugin-local/lib/rules/exported-path",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - local > should resolve > via custom path (exported through $PKG.rules[$NAME]) > absolute resolution",  # noqa: E501
)
def test_resolve_rule_local_absolute(rule_resolver: NodeResolver) -> None:
    assert rule_resolver.resolve_rule("bpmnlint-plugin-local", "exported-external-path") == {
        "path": "some-external-library",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - local > should resolve > via default location ($PKG/rules/$NAME)",  # noqa: E501
)
def test_resolve_rule_local_default(rule_resolver: NodeResolver) -> None:
    assert rule_resolver.resolve_rule("bpmnlint-plugin-local", "non-exported") == {
        "path": "./rules/non-exported",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - local > should fail to resolve > handling non-existing rule",  # noqa: E501
)
def test_resolve_rule_local_missing_rule(rule_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve rule <non-existing> from <bpmnlint-plugin-local>",
    ):
        rule_resolver.resolve_rule("bpmnlint-plugin-local", "non-existing")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveRule > plugin - local > should fail to resolve > handling illegal $PKG.rules[$NAME] export",  # noqa: E501
)
def test_resolve_rule_local_illegal(rule_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve rule <exported-invalid> from <bpmnlint-plugin-local>: illegal rule export",  # noqa: E501
    ):
        rule_resolver.resolve_rule("bpmnlint-plugin-local", "exported-invalid")


def _config_resolver() -> NodeResolver:
    def __require(path: str) -> object:
        if path == "./package.json":
            return {"name": "bpmnlint-plugin-local"}
        if path == ".":
            return {"configs": {"exported": {"path": "./lib/config/exported"}}}
        if path == "./config/non-exported":
            return {"path": path}
        if path == "bpmnlint-plugin-foreign":
            return {
                "configs": {
                    "exported": {"path": "bpmnlint-plugin-foreign/lib/config/exported"},
                },
            }
        if path == "bpmnlint-plugin-foreign/config/non-exported":
            return {"path": path}
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    def __require_local(path: str) -> object:
        if path in ("../../config/all", "../../config/recommended"):
            return {"path": path}
        msg = f"not found: {path}"
        raise ModuleNotFoundError(msg)

    return NodeResolver(
        require=_MockRequire(__require, _not_found),
        require_local=_MockRequire(__require_local, _not_found),
    )


@pytest.fixture
def config_resolver() -> NodeResolver:
    return _config_resolver()


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > built-in > all",
)
def test_resolve_config_builtin_all(config_resolver: NodeResolver) -> None:
    assert config_resolver.resolve_config("bpmnlint", "all") == {"path": "../../config/all"}


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > built-in > recommended",
)
def test_resolve_config_builtin_recommended(config_resolver: NodeResolver) -> None:
    assert config_resolver.resolve_config("bpmnlint", "recommended") == {
        "path": "../../config/recommended",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > built-in > should fail to resolve",
)
def test_resolve_config_builtin_fail(config_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve config <non-existing> from <bpmnlint>",
    ):
        config_resolver.resolve_config("bpmnlint", "non-existing")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > plugin - foreign > should resolve > exported ($PKG.configs[$NAME])",  # noqa: E501
)
def test_resolve_config_foreign_exported(config_resolver: NodeResolver) -> None:
    assert config_resolver.resolve_config("bpmnlint-plugin-foreign", "exported") == {
        "path": "bpmnlint-plugin-foreign/lib/config/exported",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > plugin - foreign > should resolve > non-exported ($PKG/config/$NAME)",  # noqa: E501
)
def test_resolve_config_foreign_non_exported(config_resolver: NodeResolver) -> None:
    assert config_resolver.resolve_config("bpmnlint-plugin-foreign", "non-exported") == {
        "path": "bpmnlint-plugin-foreign/config/non-exported",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > plugin - foreign > should fail to resolve (non-existing plugin)",  # noqa: E501
)
def test_resolve_config_foreign_missing_plugin(config_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve config <exported> from <bpmnlint-plugin-non-existing>",
    ):
        config_resolver.resolve_config("bpmnlint-plugin-non-existing", "exported")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > plugin - foreign > should fail to resolve (non-existing config)",  # noqa: E501
)
def test_resolve_config_foreign_missing_config(config_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve config <non-existing> from <bpmnlint-plugin-foreign>",
    ):
        config_resolver.resolve_config("bpmnlint-plugin-foreign", "non-existing")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > plugin - local > should resolve > exported ($PKG.configs[$NAME])",  # noqa: E501
)
def test_resolve_config_local_exported(config_resolver: NodeResolver) -> None:
    assert config_resolver.resolve_config("bpmnlint-plugin-local", "exported") == {
        "path": "./lib/config/exported",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > plugin - local > should resolve > non-exported ($PKG/config/$NAME)",  # noqa: E501
)
def test_resolve_config_local_non_exported(config_resolver: NodeResolver) -> None:
    assert config_resolver.resolve_config("bpmnlint-plugin-local", "non-exported") == {
        "path": "./config/non-exported",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/node-resolver-spec.mjs",
    "resolver/node-resolver > #resolveConfig > plugin - local > should fail to resolve",
)
def test_resolve_config_local_fail(config_resolver: NodeResolver) -> None:
    with pytest.raises(
        ValueError,
        match="cannot resolve config <non-existing> from <bpmnlint-plugin-local>",
    ):
        config_resolver.resolve_config("bpmnlint-plugin-local", "non-existing")


@pytest.fixture
def static_resolver() -> StaticResolver:
    return StaticResolver(
        {
            "rule:bpmnlint/label-required": "RULE",
            "config:bpmnlint/recommended": "CONFIG",
        },
    )


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/static-resolver-spec.mjs",
    "resolver/static-resolver > #resolveRule > should resolve rule",
)
def test_static_resolve_rule(static_resolver: StaticResolver) -> None:
    assert static_resolver.resolve_rule("bpmnlint", "label-required") == "RULE"


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/static-resolver-spec.mjs",
    "resolver/static-resolver > #resolveRule > should throw on unresolved rule",
)
def test_static_resolve_rule_unresolved(static_resolver: StaticResolver) -> None:
    with pytest.raises(ValueError, match="unknown rule <bpmnlint/non-existing-rule>"):
        static_resolver.resolve_rule("bpmnlint", "non-existing-rule")


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/static-resolver-spec.mjs",
    "resolver/static-resolver > #resolveConfig > should resolve config",
)
def test_static_resolve_config(static_resolver: StaticResolver) -> None:
    assert static_resolver.resolve_config("bpmnlint", "recommended") == "CONFIG"


@pytest.mark.upstream(
    "bpmnlint/test/spec/resolver/static-resolver-spec.mjs",
    "resolver/static-resolver > #resolveConfig > should throw on unresolved config",
)
def test_static_resolve_config_unresolved(static_resolver: StaticResolver) -> None:
    with pytest.raises(ValueError, match="unknown config <bpmnlint/non-existing-config>"):
        static_resolver.resolve_config("bpmnlint", "non-existing-config")
