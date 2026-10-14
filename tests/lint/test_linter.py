"""Ported tests for ``bpmn_io.lint.linter`` (upstream ``test/spec/linter-spec.mjs``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io._bpmnlint_utils import is_
from bpmn_io._js import UNDEFINED
from bpmn_io.lint.linter import Linter
from bpmn_io.lint.testers.helper import read_moddle
from tests.conftest import upstream_dir

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

SPEC = upstream_dir("bpmnlint") / "test" / "spec"


@pytest.fixture
def moddle_root() -> ModdleElement:
    return read_moddle(SPEC / "diagram.bpmn")["root"]


def _fake_resolver(cache: dict[str, object] | None = None) -> object:
    cache = cache or {}

    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:
            return cache.get(f"{pkg}-{rule_name}")

        def resolve_config(self, pkg: str, config_name: str) -> object:
            return cache.get(f"config-{pkg}-{config_name}")

    return _Resolver()


def _fake_rule(config: object = None) -> dict[str, object]:
    message = (config or {}).get("message") if isinstance(config, dict) else None

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if is_(node, "Definitions"):
            reporter.report(node.get("id"), message or "Definitions detected")

    return {"check": check}


def _fake_enter_leave_rule(config: object = None) -> dict[str, object]:  # noqa: ARG001
    seen: dict[object, ModdleElement] = {}

    def enter(node: ModdleElement, reporter: Reporter) -> None:  # noqa: ARG001
        node_id = node.get("id")
        if node_id:
            seen[node_id] = node

    def leave(node: ModdleElement, reporter: Reporter) -> None:
        node_id = node.get("id")
        if node_id:
            assert seen[node_id] is node
        if is_(node, "Definitions") and node_id in seen:
            reporter.report(node_id, "Definitions seen")

    return {"check": {"enter": enter, "leave": leave}}


def _build_fake_results(
    category: str | None,
    message: str | None = None,
    meta: object = UNDEFINED,
    *,
    seen: bool = False,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = [
        {
            "id": "sid-38422fae-e03e-43a3-bef4-bd33b32041b2",
            "message": message or ("Definitions seen" if seen else "Definitions detected"),
        },
    ]
    if category is None:
        return results
    return [{**result, "category": category, "meta": meta} for result in results]


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > constructor > should require { resolver } config",
)
def test_constructor_requires_resolver() -> None:
    with pytest.raises(ValueError, match="must provide <options.resolver>"):  # noqa: RUF043
        Linter()


@pytest.mark.upstream("bpmnlint/test/spec/linter-spec.mjs", "linter > #applyRule > should succeed")
def test_apply_rule_succeed(moddle_root: ModdleElement) -> None:
    linter = Linter(resolver=_fake_resolver())
    results = linter.apply_rule(
        moddle_root,
        {"name": "test-rule", "config": {}, "rule": _fake_rule(), "category": "error"},
    )
    assert results == _build_fake_results("error")


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #applyRule > should succeed with <enter> and <leave> hooks",
)
def test_apply_rule_enter_leave(moddle_root: ModdleElement) -> None:
    linter = Linter(resolver=_fake_resolver())
    results = linter.apply_rule(
        moddle_root,
        {"name": "test-rule", "config": {}, "rule": _fake_enter_leave_rule(), "category": "error"},
    )
    assert results == _build_fake_results("error", seen=True)


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #applyRule > should fail with rule error"
)
def test_apply_rule_fails_with_rule_error(moddle_root: ModdleElement) -> None:
    def check(node: ModdleElement, reporter: Reporter) -> None:  # noqa: ARG001
        msg = "foo"
        raise RuntimeError(msg)

    linter = Linter(resolver=_fake_resolver())
    results = linter.apply_rule(
        moddle_root,
        {"name": "test-rule", "config": {}, "rule": {"check": check}, "category": "warn"},
    )
    assert results == [{"category": "rule-error", "message": "foo"}]


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #applyRule > should fail without check"
)
def test_apply_rule_fails_without_check(moddle_root: ModdleElement) -> None:
    linter = Linter(resolver=_fake_resolver())
    results = linter.apply_rule(
        moddle_root,
        {"name": "test-rule", "config": {}, "rule": {}, "category": "warn"},
    )
    assert results == [{"category": "rule-error", "message": "no check implemented"}]


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #applyRule > should fail without <enter> or <leave> hook",
)
def test_apply_rule_fails_without_hooks(moddle_root: ModdleElement) -> None:
    linter = Linter(resolver=_fake_resolver())
    results = linter.apply_rule(
        moddle_root,
        {"name": "test-rule", "config": {}, "rule": {"check": {}}, "category": "warn"},
    )
    assert results == [{"category": "rule-error", "message": "no check implemented"}]


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #lint > config > should apply global config"
)
def test_lint_global_config(moddle_root: ModdleElement) -> None:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:  # noqa: ARG002
            msg = "unexpected invocation"
            raise AssertionError(msg)

    linter = Linter(resolver=_Resolver(), config={})
    assert linter.lint(moddle_root) == {}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #lint > config > should apply local config"
)
def test_lint_local_config(moddle_root: ModdleElement) -> None:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:  # noqa: ARG002
            msg = "unexpected invocation"
            raise AssertionError(msg)

    linter = Linter(resolver=_Resolver(), config={"rules": {"nonExistingRule": "warn"}})
    assert linter.lint(moddle_root, {}) == {}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #lint > rules > should resolve"
)
def test_lint_resolve(moddle_root: ModdleElement) -> None:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:
            assert pkg == "bpmnlint"
            assert rule_name == "testRule"
            return _fake_rule

    linter = Linter(resolver=_Resolver())
    results = linter.lint(moddle_root, {"rules": {"testRule": "warn"}})
    assert results == {"testRule": _build_fake_results("warn")}


@pytest.mark.parametrize("category", ["warn", "error", "info"])
@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #lint > rules > should resolve and configure > warn",
)
@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #lint > rules > should resolve and configure > error",
)
@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #lint > rules > should resolve and configure > info",
)
def test_lint_resolve_and_configure(moddle_root: ModdleElement, category: str) -> None:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:
            assert pkg == "bpmnlint"
            assert rule_name == "testRule"
            return _fake_rule

    linter = Linter(resolver=_Resolver())
    results = linter.lint(moddle_root, {"rules": {"testRule": [category, {"message": "foo"}]}})
    assert results == {"testRule": _build_fake_results(category, "foo")}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #lint > rules > should resolve async"
)
def test_lint_resolve_async(moddle_root: ModdleElement) -> None:
    # Sync mapping (EVOL D4.1): an async rule factory upstream is a plain
    # factory in the synchronous port.
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:  # noqa: ARG002
            return _fake_rule

    linter = Linter(resolver=_Resolver())
    results = linter.lint(moddle_root, {"rules": {"testRule": "warn"}})
    assert results == {"testRule": _build_fake_results("warn")}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #lint > rules > should handle unresolved"
)
def test_lint_handle_unresolved(moddle_root: ModdleElement) -> None:
    class _Resolver:
        def resolve_rule(self, _pkg: str, _rule_name: str) -> object:
            return None

    linter = Linter(resolver=_Resolver())
    with pytest.raises(ValueError, match="unknown rule <unknownRule>"):
        linter.lint(moddle_root, {"rules": {"unknownRule": "warn"}})


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #lint > rules > should not resolve disabled"
)
def test_lint_not_resolve_disabled(moddle_root: ModdleElement) -> None:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:  # noqa: ARG002
            msg = "unexpected resolve call"
            raise AssertionError(msg)

    linter = Linter(resolver=_Resolver(), config={"rules": {"unknownRule": "off"}})
    assert linter.lint(moddle_root) == {}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseRuleValue > should extract { category, config }",
)
def test_parse_rule_value() -> None:
    linter = Linter(resolver=_fake_resolver())
    assert linter.parse_rule_value(0) == {"category": "off", "config": {}}
    assert linter.parse_rule_value([0, "A"]) == {"category": "off", "config": "A"}
    assert linter.parse_rule_value(1) == {"category": "warn", "config": {}}
    assert linter.parse_rule_value(2) == {"category": "error", "config": {}}
    assert linter.parse_rule_value(3) == {"category": "info", "config": {}}


def _extended_resolver() -> object:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:
            assert pkg == "bpmnlint"
            assert rule_name == "foo"
            return lambda config=None: {"check": lambda _node, _reporter: None}  # noqa: ARG005

        def resolve_config(self, pkg: str, config_name: str) -> object:
            assert pkg == "bpmnlint"
            assert config_name == "recommended"
            return {"rules": {"foo": "warn"}}

    return _Resolver()


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #resolveConfiguredRules > should resolve extended > single parent",
)
def test_resolve_extended_single_parent() -> None:
    linter = Linter(resolver=_extended_resolver())
    rules = linter.resolve_configured_rules({"extends": "bpmnlint:recommended"})
    assert rules == {"foo": "warn"}


def _multi_parent_resolver() -> object:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:  # noqa: ARG002
            return lambda config=None: {"check": lambda _node, _reporter: None}  # noqa: ARG005

        def resolve_config(self, pkg: str, config_name: str) -> object:
            if pkg == "bpmnlint" and config_name == "recommended":
                return {"rules": {"foo": "warn", "bar": "warn"}}
            if pkg == "bpmnlint-plugin-test":
                if config_name == "recommended":
                    return {
                        "extends": "plugin:test/base",
                        "rules": {"test/bar": "warn", "other": "info"},
                    }
                if config_name == "base":
                    return {
                        "rules": {"bpmnlint/bar": "error", "bar": "error", "other": "error"},
                    }
            msg = f"unexpected config <{config_name}>"
            raise AssertionError(msg)

    return _Resolver()


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #resolveConfiguredRules > should resolve extended > multiple parents > should resolve extended",  # noqa: E501
)
def test_resolve_extended_multiple_parents() -> None:
    linter = Linter(resolver=_multi_parent_resolver())
    rules = linter.resolve_configured_rules(
        {"extends": ["bpmnlint:recommended", "plugin:test/recommended"]},
    )
    assert rules == {"bar": "error", "foo": "warn", "test/bar": "warn", "test/other": "info"}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #resolveConfiguredRules > should resolve extended > multiple parents > should normalize rule names",  # noqa: E501
)
def test_resolve_extended_normalize_rule_names() -> None:
    linter = Linter(resolver=_multi_parent_resolver())
    rules = linter.resolve_configured_rules(
        {
            "extends": ["bpmnlint:recommended", "plugin:test/recommended"],
            "rules": {"bpmnlint/foo": "error", "foo": "error", "test/bar": "off"},
        },
    )
    assert rules == {"bar": "error", "foo": "error", "test/bar": "off", "test/other": "info"}


def _scoped_resolver() -> object:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:  # noqa: ARG002
            return lambda config=None: {"check": lambda _node, _reporter: None}  # noqa: ARG005

        def resolve_config(self, pkg: str, config_name: str) -> object:
            if pkg == "bpmnlint-plugin-test" and config_name == "recommended":
                return {"rules": {"@ns/bpmnlint-plugin-test/bar": "warn"}}
            if pkg == "@ns/bpmnlint-plugin-test":
                if config_name == "recommended":
                    return {"rules": {"bar": "off"}}
                if config_name == "other":
                    return {"rules": {"foo": "warn"}}
            msg = f"unexpected config <{config_name}>"
            raise AssertionError(msg)

    return _Resolver()


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #resolveConfiguredRules > should resolve extended > scoped > should normalize shortcut",  # noqa: E501
)
def test_resolve_scoped_normalize_shortcut() -> None:
    linter = Linter(resolver=_scoped_resolver())
    rules = linter.resolve_configured_rules(
        {
            "extends": ["plugin:@ns/test/other"],
            "rules": {"@ns/bpmnlint-plugin-test/foo": "error"},
        },
    )
    assert rules == {"@ns/test/foo": "error"}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #resolveConfiguredRules > should resolve extended > scoped > should normalize full package name",  # noqa: E501
)
def test_resolve_scoped_normalize_full() -> None:
    linter = Linter(resolver=_scoped_resolver())
    rules = linter.resolve_configured_rules(
        {
            "extends": ["plugin:@ns/bpmnlint-plugin-test/other"],
            "rules": {"@ns/test/foo": "error"},
        },
    )
    assert rules == {"@ns/test/foo": "error"}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #resolveConfiguredRules > should resolve extended > scoped > should normalize multiple",  # noqa: E501
)
def test_resolve_scoped_normalize_multiple() -> None:
    linter = Linter(resolver=_scoped_resolver())
    rules = linter.resolve_configured_rules(
        {
            "extends": [
                "plugin:@ns/test/other",
                "plugin:@ns/bpmnlint-plugin-test/recommended",
                "plugin:test/recommended",
            ],
            "rules": {
                "@ns/bpmnlint-plugin-test/bar": "off",
                "@ns/bpmnlint-plugin-test/foo": "error",
            },
        },
    )
    assert rules == {"@ns/test/foo": "error", "@ns/test/bar": "off"}


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #resolveConfiguredRules > should throw on missing",
)
def test_resolve_configured_rules_throw_on_missing() -> None:
    class _Resolver:
        def resolve_config(self, _pkg: str, _config_name: str) -> object:
            return None

    linter = Linter(resolver=_Resolver())
    with pytest.raises(ValueError, match="unknown config <plugin:foo/bar>"):
        linter.resolve_configured_rules({"extends": "plugin:foo/bar"})


@pytest.fixture
def plain_linter() -> Linter:
    return Linter(resolver=_fake_resolver())


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #parseRuleName > should parse built-in"
)
def test_parse_rule_name_builtin(plain_linter: Linter) -> None:
    assert plain_linter.parse_rule_name("bpmnlint/label-required") == {
        "pkg": "bpmnlint",
        "rule_name": "label-required",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseRuleName > should parse built-in without prefix",
)
def test_parse_rule_name_builtin_without_prefix(plain_linter: Linter) -> None:
    assert plain_linter.parse_rule_name("label-required") == {
        "pkg": "bpmnlint",
        "rule_name": "label-required",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #parseRuleName > should parse external"
)
def test_parse_rule_name_external(plain_linter: Linter) -> None:
    assert plain_linter.parse_rule_name("foo/label-required") == {
        "pkg": "bpmnlint-plugin-foo",
        "rule_name": "label-required",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseRuleName > should parse external with full package name",
)
def test_parse_rule_name_external_full(plain_linter: Linter) -> None:
    assert plain_linter.parse_rule_name("bpmnlint-plugin-foo/label-required") == {
        "pkg": "bpmnlint-plugin-foo",
        "rule_name": "label-required",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #parseRuleName > should parse scoped"
)
def test_parse_rule_name_scoped(plain_linter: Linter) -> None:
    assert plain_linter.parse_rule_name("@scoped/bpmnlint-plugin-foo/label-required") == {
        "pkg": "@scoped/bpmnlint-plugin-foo",
        "rule_name": "label-required",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseRuleName > should parse scoped with full package name",
)
def test_parse_rule_name_scoped_full(plain_linter: Linter) -> None:
    assert plain_linter.parse_rule_name("@scoped/foo/label-required") == {
        "pkg": "@scoped/bpmnlint-plugin-foo",
        "rule_name": "label-required",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseRuleName > should fail to parse with missing package",
)
def test_parse_rule_name_missing_package(plain_linter: Linter) -> None:
    with pytest.raises(ValueError, match="unparseable rule name <@scoped/label-required>"):
        plain_linter.parse_rule_name("@scoped/label-required")


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #parseRuleName > should fail to parse nonsense"
)
def test_parse_rule_name_nonsense(plain_linter: Linter) -> None:
    with pytest.raises(ValueError, match="unparseable rule name <foo/bar/goings>"):
        plain_linter.parse_rule_name("foo/bar/goings")


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #parseConfigName > should parse built-in > all"
)
def test_parse_config_name_all(plain_linter: Linter) -> None:
    assert plain_linter.parse_config_name("bpmnlint:all") == {
        "pkg": "bpmnlint",
        "config_name": "all",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseConfigName > should parse built-in > recommended",
)
def test_parse_config_name_recommended(plain_linter: Linter) -> None:
    assert plain_linter.parse_config_name("bpmnlint:recommended") == {
        "pkg": "bpmnlint",
        "config_name": "recommended",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #parseConfigName > should parse external"
)
def test_parse_config_name_external(plain_linter: Linter) -> None:
    assert plain_linter.parse_config_name("plugin:foo/bar") == {
        "pkg": "bpmnlint-plugin-foo",
        "config_name": "bar",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseConfigName > should parse external with full package name",
)
def test_parse_config_name_external_full(plain_linter: Linter) -> None:
    assert plain_linter.parse_config_name("plugin:bpmnlint-plugin-foo/bar") == {
        "pkg": "bpmnlint-plugin-foo",
        "config_name": "bar",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #parseConfigName > should parse scoped"
)
def test_parse_config_name_scoped(plain_linter: Linter) -> None:
    assert plain_linter.parse_config_name("plugin:@ns/foo/bar") == {
        "pkg": "@ns/bpmnlint-plugin-foo",
        "config_name": "bar",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseConfigName > should parse scoped with full package name",
)
def test_parse_config_name_scoped_full(plain_linter: Linter) -> None:
    assert plain_linter.parse_config_name("plugin:@ns/bpmnlint-plugin-foo/bar") == {
        "pkg": "@ns/bpmnlint-plugin-foo",
        "config_name": "bar",
    }


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > #parseConfigName > should throw on invalid name"
)
def test_parse_config_name_invalid(plain_linter: Linter) -> None:
    with pytest.raises(ValueError, match="unparseable config name <foo:bar>"):
        plain_linter.parse_config_name("foo:bar")


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseConfigName > should throw error on invalid scoped name",
)
def test_parse_config_name_invalid_scoped(plain_linter: Linter) -> None:
    with pytest.raises(ValueError, match="unparseable config name <plugin:@ns/not-valid>"):
        plain_linter.parse_config_name("plugin:@ns/not-valid")


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseConfigName > should throw error on namespaced default config",
)
def test_parse_config_name_namespaced_default(plain_linter: Linter) -> None:
    with pytest.raises(ValueError, match="unparseable config name <bpmnlint:@ns/not-valid>"):
        plain_linter.parse_config_name("bpmnlint:@ns/not-valid")


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > #parseConfigName > should throw error on non-sense name",
)
def test_parse_config_name_nonsense(plain_linter: Linter) -> None:
    with pytest.raises(ValueError, match="unparseable config name <bpmnlint:asd/not-valid/asd>"):
        plain_linter.parse_config_name("bpmnlint:asd/not-valid/asd")


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs", "linter > reporting > should attach rule <meta> to report"
)
def test_attach_meta_to_report(moddle_root: ModdleElement) -> None:
    meta = {"foo": "BAR"}
    rule = {**_fake_rule(), "meta": meta}
    linter = Linter(resolver=_fake_resolver())
    results = linter.apply_rule(
        moddle_root,
        {"name": "test-rule", "config": {}, "rule": rule, "category": "error"},
    )
    assert results == _build_fake_results("error", meta=meta)


@pytest.mark.upstream(
    "bpmnlint/test/spec/linter-spec.mjs",
    "linter > rule transformation > should transform rules via hook",
)
def test_transform_rules_via_hook(moddle_root: ModdleElement) -> None:
    class _Resolver:
        def resolve_rule(self, pkg: str, rule_name: str) -> object:
            assert pkg == "bpmnlint"
            assert rule_name == "testRule"
            return _fake_rule

        def resolve_config(self, pkg: str, config_name: str) -> object:
            assert pkg == "bpmnlint"
            assert config_name == "recommended"
            return {"rules": {"testRule": "error"}}

    meta = {"foo": "BAR"}

    def transform_rule(rule: dict[str, object], rule_meta: dict[str, object]) -> dict[str, object]:
        assert rule_meta == {"pkg": "bpmnlint", "ruleName": "testRule"}
        return {**rule, "meta": meta}

    linter = Linter(resolver=_Resolver(), transform_rule=transform_rule)
    results = linter.lint(moddle_root, {"extends": "bpmnlint:recommended"})
    assert results == {"testRule": _build_fake_results("error", meta=meta)}
