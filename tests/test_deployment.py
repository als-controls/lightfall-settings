import pytest

from lightfall_settings import (
    CORE_SPECS,
    DEPLOYMENT_SPECS,
    ScopeId,
    ScopeSnapshot,
    core_registry,
    deployment_registry,
    resolve,
    spec_from_dict,
    spec_to_dict,
)

BL = ScopeId("beamline", "7.0.1")
BR = ScopeId("branch", "7.0.1.1")
USER = ScopeId("user", "ron")
FAC = ScopeId("facility")

IDENTITY = ("tiled_beamline", "current_beamline", "ipc_topic_prefix")


def row(rid: str, **config) -> dict:
    return {"id": rid, "type": "happi", "name": rid, "enabled": True, "config": config}


def test_deployment_specs_are_not_core():
    core = core_registry()
    assert not any(core.is_declared(s.key) for s in DEPLOYMENT_SPECS)


def test_deployment_registry_has_core_and_deployment_specs():
    reg = deployment_registry()
    for spec in (*CORE_SPECS, *DEPLOYMENT_SPECS):
        assert reg.is_declared(spec.key)


@pytest.mark.parametrize("key", IDENTITY)
def test_identity_keys_live_at_beamline_and_branch_only(key):
    spec = deployment_registry().get(key)
    assert spec.scopes == frozenset({"beamline", "branch"})
    assert spec.write_role == "maintainer"


def test_user_value_of_identity_key_is_ignored():
    """The 7.0.1.1 incident: a user-scope tiled_beamline must not beat the beamline's."""
    spec = deployment_registry().get("tiled_beamline")
    res = resolve(spec, [
        ScopeSnapshot(FAC),
        ScopeSnapshot(BL, {"tiled_beamline": "7.0.1"}),
        ScopeSnapshot(BR, {"tiled_beamline": "7.0.1.1"}),
        ScopeSnapshot(USER, {"tiled_beamline": "12.0.2.1"}),
    ])
    assert res.value == "7.0.1.1"
    assert res.origin == BR


@pytest.mark.parametrize("key", ["device_backends", "device_backends_exclusive_restore"])
def test_device_row_keys_are_union_at_beamline_branch_user(key):
    spec = deployment_registry().get(key)
    assert spec.policy == "union"
    assert spec.scopes == frozenset({"beamline", "branch", "user"})
    assert not spec.subtractable
    assert spec.write_role == "maintainer"


def test_device_backends_rows_merge_by_id():
    spec = deployment_registry().get("device_backends")
    res = resolve(spec, [
        ScopeSnapshot(FAC),
        ScopeSnapshot(BL, {"device_backends": {"a": row("a", path="/bl.json")}}),
        ScopeSnapshot(BR, {"device_backends": {"b": row("b", path="/br.json")}}),
        ScopeSnapshot(USER, {"device_backends": {
            "a": {**row("a", path="/bl.json"), "enabled": False},
            "c": row("c", path="/mine.json"),
        }}),
    ])
    assert set(res.value) == {"a", "b", "c"}
    assert res.value["a"]["enabled"] is False  # a user may override an item, per item
    assert res.item_origins == {"a": USER, "b": BR, "c": USER}


def test_list_shaped_device_backends_are_rejected():
    spec = deployment_registry().get("device_backends")
    with pytest.raises(ValueError, match="union value must be an object"):
        spec.validate([row("a")])


def test_users_cannot_remove_beamline_rows():
    spec = deployment_registry().get("device_backends")
    with pytest.raises(ValueError, match="cannot be removed"):
        spec.validate({"a": None})


def test_exclusive_restore_items_are_bools():
    spec = deployment_registry().get("device_backends_exclusive_restore")
    assert spec.validate({"a": True}) == {"a": True}
    with pytest.raises(ValueError):
        spec.validate({"a": "yes"})


def test_deployment_specs_round_trip_through_json():
    for spec in DEPLOYMENT_SPECS:
        assert spec_from_dict(spec_to_dict(spec)) == spec
