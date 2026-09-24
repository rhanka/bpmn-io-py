"""Conformance of the committed stub against the descriptors and the runtime."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.bpmn_moddle.types import is_a

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent.parent
STUB = ROOT / "src" / "bpmn_io" / "bpmn_moddle" / "types.pyi"
GEN = ROOT / "scripts" / "gen_stubs.py"
MODULE = "bpmn_io.bpmn_moddle.types"


def load_generator() -> ModuleType:
    """Import scripts/gen_stubs.py by path (single source of truth)."""
    spec = importlib.util.spec_from_file_location("gen_stubs", GEN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stub_covers_every_concrete_type() -> None:
    """The committed stub names every concrete descriptor type exactly once."""
    gen = load_generator()
    concrete, _enums, _skipped = gen.collect()
    expected_quals = sorted(str(info["qual"]) for info in concrete)
    expected_classes = sorted(str(info["class"]) for info in concrete)
    text = STUB.read_text(encoding="utf-8")

    literals = sorted(set(re.findall(r'"([a-z]+:[A-Za-z]+)"', text)))
    assert literals == expected_quals

    classes = sorted(set(re.findall(r"^class (\w+)\(", text, flags=re.MULTILINE)))
    assert "TypedBpmnModdle" in classes
    assert sorted(name for name in classes if name != "TypedBpmnModdle") == expected_classes

    assert text.count("@overload") == 2 * (len(expected_quals) + 1)
    assert "\n    from:" not in text
    assert "\n    import:" not in text


def test_stub_mapping_spot_checks() -> None:
    """Pin the class-name rule and superClass bases on known types."""
    text = STUB.read_text(encoding="utf-8")
    assert "class BpmnServiceTask(BpmnTask):" in text
    assert "class BpmnTask(BpmnActivity, BpmnInteractionNode):" in text
    assert "class BpmnSubProcess(BpmnActivity, BpmnFlowElementsContainer" in text
    assert "class BpmndiBPMNShape(DiLabeledShape):" in text
    assert "class DiShape(DiNode):" in text
    assert "class DcBounds(ModdleElement):" in text
    assert "class TypedBpmnModdle(BpmnModdle):" in text


def test_stubtest_clean(tmp_path: Path) -> None:
    """stubtest passes; typing-only names are allowlisted by exact match."""
    pytest.importorskip("mypy.stubtest")
    gen = load_generator()
    concrete, _enums, _skipped = gen.collect()
    # Allowlist entries fullmatch the bare dotted path (mismatch messages differ).
    names = [str(info["class"]) for info in concrete] + ["TypedBpmnModdle", "BpmnTypeName"]
    patterns = [f"{MODULE}.{name}" for name in names]
    patterns.append(f"{MODULE}.__all__")
    allowlist = tmp_path / "allowlist.txt"
    allowlist.write_text("\n".join(patterns) + "\n", encoding="utf-8")
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell.
        [sys.executable, "-m", "mypy.stubtest", MODULE, "--allowlist", str(allowlist)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, f"stubtest failed:\n{proc.stdout}\n{proc.stderr}"


def test_every_literal_creates_and_narrows() -> None:
    """Every stub literal creates through the model and narrows through is_a."""
    gen = load_generator()
    concrete, _enums, _skipped = gen.collect()
    assert len(concrete) > 150
    model = create_moddle()
    for info in concrete:
        element = model.create(str(info["qual"]))
        assert element.type_ == info["qual"]
        assert is_a(element, str(info["qual"])) is True
    task = model.create("bpmn:Task")
    assert is_a(task, "bpmn:Activity") is True
    assert is_a(task, "bpmn:Process") is False
    assert is_a(None, "bpmn:Task") is False
    assert is_a("bpmn:Task", "bpmn:Task") is False
