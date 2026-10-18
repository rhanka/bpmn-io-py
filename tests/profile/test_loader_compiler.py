"""Loader and compiler parity over the neutral fixtures."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"

Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None


def _read(name: str) -> bytes:
    return (MECHANISM / name).read_bytes()


def _load_neutral() -> tuple[Json, Json, Json, Json]:
    from bpmn_io.profile import load_profile

    profile_bytes = _read("neutral-profile.json")
    schema_bytes = _read("profile-mechanism-1.schema.json")
    base_bytes = _read("neutral-base.json")
    metrics_bytes = _read("neutral-metrics.json")
    profile = json.loads(profile_bytes.decode("utf-8"))
    assert isinstance(profile, dict)
    descriptors = profile["descriptors"]
    assert isinstance(descriptors, list)
    capabilities = profile["capabilities"]
    assert isinstance(capabilities, list)
    result = load_profile(
        profile_bytes,
        schema_bytes=schema_bytes,
        descriptor_pins=descriptors,  # type: ignore[arg-type]
        base_bytes=base_bytes,
        asset_bag={"neutral-metrics.json": metrics_bytes},
        capabilities=[str(c) for c in capabilities],
    )
    assert result.status == "ok", result
    assert isinstance(result.payload, object)
    return profile, schema_bytes, base_bytes, metrics_bytes


def test_neutral_profile_loads_with_pins() -> None:
    """The neutral profile loads with its pinned base, descriptors and assets."""
    from bpmn_io.profile import digest

    profile, _, _, _ = _load_neutral()
    assert isinstance(profile, dict)
    assert digest(profile["base"]) != ""
    assert profile["mechanismVersion"] == "1"
    assert profile["schemaVersion"] == "1.0.0"


def test_neutral_profile_substitution_matches() -> None:
    """Neutral and grid-neutral profiles load and compile identically shaped."""
    from bpmn_io.profile import compile_profile, load_profile

    for name in ("neutral-profile.json", "neutral-grid-profile.json"):
        profile_bytes = _read(name)
        schema_bytes = _read("profile-mechanism-1.schema.json")
        profile = json.loads(profile_bytes.decode("utf-8"))
        assert isinstance(profile, dict)
        descriptors = profile["descriptors"]
        capabilities = profile["capabilities"]
        assert isinstance(descriptors, list)
        assert isinstance(capabilities, list)
        loaded = load_profile(
            profile_bytes,
            schema_bytes=schema_bytes,
            descriptor_pins=descriptors,  # type: ignore[arg-type]
            capabilities=[str(c) for c in capabilities],
        )
        assert loaded.status == "ok", f"{name}: {loaded}"
        assert loaded.payload is not None
        compiled = compile_profile(loaded.payload)  # type: ignore[arg-type]
        assert compiled.status == "ok", f"{name}: {compiled}"
        assert compiled.payload is not None
        payload = compiled.payload
        assert payload.profile_digest != ""  # type: ignore[union-attr]


def test_loader_rejects_bad_base_pin() -> None:
    """A mismatched base digest refuses with the pin code."""
    from bpmn_io.profile import load_profile

    profile_bytes = _read("neutral-profile.json")
    schema_bytes = _read("profile-mechanism-1.schema.json")
    result = load_profile(
        profile_bytes,
        schema_bytes=schema_bytes,
        base_bytes=b"{}",
    )
    assert result.status == "refused"
    assert result.code == "profile-pin"  # type: ignore[union-attr]


def test_loader_needs_codec_boundary_documented() -> None:
    """Envelope import decodes document JSON through the wired codec default."""
    from bpmn_io.profile import import_envelope

    profile = json.loads(_read("neutral-profile.json").decode("utf-8"))
    assert isinstance(profile, dict)
    identity = {
        "mechanismVersion": "1",
        "schemaVersion": "1.0.0",
        "profile": profile["profile"],
        "version": profile["version"],
        "sha256": "00" * 32,
        "base": profile["base"],
        "descriptors": profile["descriptors"],
    }
    wired = import_envelope(b'{"tree": {}}', identity)  # type: ignore[arg-type]
    assert wired.status == "ok"
    refused = import_envelope(b"not json", identity)  # type: ignore[arg-type]
    assert refused.status == "refused"
    assert refused.code == "document-not-loaded"  # type: ignore[union-attr]


def test_compiler_rejects_unknown_operator() -> None:
    """An unknown predicate operator refuses with the symbol code."""
    from bpmn_io.profile import compile_profile

    _, _, _, _ = _load_neutral()
    from bpmn_io.profile import load_profile

    profile = json.loads(_read("neutral-profile.json").decode("utf-8"))
    assert isinstance(profile, dict)
    profile["rules"] = [
        {
            "id": "bad",
            "stage": "post-normalize",
            "select": {"from": "root", "via": "self", "where": {"op": "true"}, "order": "id"},
            "bindings": [],
            "assert": {"op": "frobnicate"},
            "report": {"messageKey": "bad"},
        }
    ]
    schema_bytes = _read("profile-mechanism-1.schema.json")
    loaded = load_profile(json.dumps(profile).encode("utf-8"), schema_bytes=schema_bytes)
    # The closed schema pins every operator, so the unknown op refuses here.
    assert loaded.status == "refused", loaded
    assert loaded.code == "profile-schema"  # type: ignore[union-attr]
    # The compiler owns the same refusal for inputs bypassing the loader.
    from bpmn_io.profile._loader import ValidatedProfile

    direct = ValidatedProfile(
        profile=profile,
        digest="test",
        schema_id="urn:profile-mechanism:1:profile",
        base={},
        descriptors=[],
        capabilities=[],
    )
    compiled = compile_profile(direct)
    assert compiled.status == "refused"
    assert compiled.code == "profile-symbol"  # type: ignore[union-attr]


def test_compiler_outcomes_identical_on_fixtures() -> None:
    """Compiling each neutral fixture twice yields identical digests."""
    from bpmn_io.profile import compile_profile, load_profile

    for name in (
        "neutral-profile.json",
        "neutral-grid-profile.json",
        "neutral-profile.v1.json",
        "neutral-grid-profile.v1.json",
    ):
        path = MECHANISM / name
        if not path.is_file():
            continue
        profile_bytes = path.read_bytes()
        schema_bytes = _read("profile-mechanism-1.schema.json")
        first = load_profile(profile_bytes, schema_bytes=schema_bytes)
        second = load_profile(profile_bytes, schema_bytes=schema_bytes)
        assert first.status == "ok"
        assert second.status == "ok"
        assert first.payload is not None
        assert second.payload is not None
        first_compiled = compile_profile(first.payload)  # type: ignore[arg-type]
        second_compiled = compile_profile(second.payload)  # type: ignore[arg-type]
        assert first_compiled.status == second_compiled.status == "ok"
        assert (
            first_compiled.payload.profile_digest  # type: ignore[union-attr]
            == second_compiled.payload.profile_digest  # type: ignore[union-attr]
        )
