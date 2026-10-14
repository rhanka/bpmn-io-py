"""Adapted index tests (upstream ``test/spec/index-spec.js``).

Upstream asserts the CommonJS and ES module exports of the ``bpmnlint``
package; the Python surface is the ``bpmn_io.lint`` package and its
``linter`` submodule, both exporting ``Linter``.
"""

from __future__ import annotations

import pytest


@pytest.mark.upstream("bpmnlint/test/spec/index-spec.js", "should CJS export { Linter }")
def test_package_export_linter() -> None:
    from bpmn_io.lint import Linter

    assert Linter is not None


@pytest.mark.upstream("bpmnlint/test/spec/index-spec.js", "should ES export { Linter }")
def test_submodule_export_linter() -> None:
    from bpmn_io.lint import Linter
    from bpmn_io.lint.linter import Linter as SubmoduleLinter

    assert SubmoduleLinter is Linter
