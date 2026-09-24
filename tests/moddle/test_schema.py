"""Ported moddle JSON-schema cases (Lot 4).

Transcribes every ``moddle/test/spec/schema.js`` dynamic ``it()`` title: one
test per vendored model fixture (13 claims, titles mirror the upstream
``should validate fixture: ${file}`` template). The schema is compiled once
with ``jsonschema`` (Draft 07, as declared by the vendored schema) and each
fixture must validate cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

MODEL_FIXTURES = (
    Path(__file__).resolve().parent.parent / "upstream" / "moddle" / "test" / "fixtures" / "model"
)
SCHEMA_FILE = (
    Path(__file__).resolve().parent.parent
    / "upstream"
    / "moddle"
    / "resources"
    / "schema"
    / "moddle.json"
)

_SCHEMA: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft7Validator(_SCHEMA)


def _assert_valid(relative_path: str) -> None:
    """Assert the vendored model fixture validates against the package schema."""
    model = json.loads((MODEL_FIXTURES / relative_path).read_text(encoding="utf-8"))

    assert _VALIDATOR.is_valid(model), relative_path


@pytest.mark.upstream(
    "moddle/test/spec/schema.js",
    "should validate fixture: test/fixtures/model/datatype-external.json",
)
def test_001_validate_datatype_external() -> None:
    _assert_valid("datatype-external.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/datatype.json"
)
def test_002_validate_datatype() -> None:
    _assert_valid("datatype.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/extension/base.json"
)
def test_003_validate_extension_base() -> None:
    _assert_valid("extension/base.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js",
    "should validate fixture: test/fixtures/model/extension/custom.json",
)
def test_004_validate_extension_custom() -> None:
    _assert_valid("extension/custom.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/meta.json"
)
def test_005_validate_meta() -> None:
    _assert_valid("meta.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/noalias.json"
)
def test_006_validate_noalias() -> None:
    _assert_valid("noalias.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js",
    "should validate fixture: test/fixtures/model/properties-extended.json",
)
def test_007_validate_properties_extended() -> None:
    _assert_valid("properties-extended.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/properties.json"
)
def test_008_validate_properties() -> None:
    _assert_valid("properties.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/redefines/base.json"
)
def test_009_validate_redefines_base() -> None:
    _assert_valid("redefines/base.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/replaces/base.json"
)
def test_010_validate_replaces_base() -> None:
    _assert_valid("replaces/base.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/schema-meta.json"
)
def test_011_validate_schema_meta() -> None:
    _assert_valid("schema-meta.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/self-extend.json"
)
def test_012_validate_self_extend() -> None:
    _assert_valid("self-extend.json")


@pytest.mark.upstream(
    "moddle/test/spec/schema.js", "should validate fixture: test/fixtures/model/shadow.json"
)
def test_013_validate_shadow() -> None:
    _assert_valid("shadow.json")
