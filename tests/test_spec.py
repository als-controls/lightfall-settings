import json

import pytest
from pydantic import BaseModel

from lightfall_settings.scopes import ALL_KINDS
from lightfall_settings.spec import (
    CORE_SPECS,
    SettingSpec,
    SpecRegistry,
    core_registry,
    spec_from_dict,
    spec_to_dict,
    user_only_spec,
)


def everywhere(key: str) -> SettingSpec:
    return SettingSpec(key, scopes=ALL_KINDS)


def test_defaults_are_user_only_override():
    s = SettingSpec("theme")
    assert s.scopes == frozenset({"user"})
    assert s.policy == "override"
    assert s.allows("user") and not s.allows("beamline")


def test_scopes_accepts_any_iterable():
    s = SettingSpec("x", scopes=["facility", "branch"])
    assert s.scopes == frozenset({"facility", "branch"})


def test_required_role():
    assert SettingSpec("a", scopes=ALL_KINDS).required_role("beamline") == "maintainer"
    assert SettingSpec("a", scopes=ALL_KINDS, operator_writable=True).required_role(
        "branch") == "operator"
    s = SettingSpec("a", scopes=ALL_KINDS, write_role={"facility": "admin"})
    assert s.required_role("facility") == "admin"
    assert s.required_role("beamline") == "maintainer"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"key": ""},
        {"key": "a", "scopes": []},
        {"key": "a", "scopes": ["galaxy"]},
        {"key": "a", "subtractable": True},
        {"key": "a", "write_role": "superuser"},
        {"key": "a", "write_role": {"beamline": "superuser"}},
        {"key": "a", "write_role": {"galaxy": "admin"}},
        {"key": "a", "policy": "append"},
        {"key": "a", "write_role": "viewer"},
        {"key": "a", "write_role": {"branch": "viewer"}},
    ],
)
def test_invalid_specs_rejected(kwargs):
    with pytest.raises(ValueError):
        SettingSpec(**kwargs)


def test_validate_override():
    s = SettingSpec("tiled.url", type=str)
    assert s.validate("https://tiled") == "https://tiled"
    with pytest.raises(ValueError):
        s.validate(3)


def test_validate_untyped_accepts_anything():
    assert SettingSpec("legacy").validate({"a": [1, 2]}) == {"a": [1, 2]}


def test_validate_union():
    s = SettingSpec("plugins.enabled", type=bool, scopes=ALL_KINDS, policy="union")
    assert s.validate({"deck": True}) == {"deck": True}
    for bad in ([True], "deck", {"deck": "maybe-not-bool-ish-string"}, {1: True}):
        with pytest.raises(ValueError):
            s.validate(bad)
    with pytest.raises(ValueError):
        s.validate({"deck": None})  # tombstone, not subtractable


def test_validate_union_tombstone_when_subtractable():
    s = SettingSpec("p", type=bool, scopes=ALL_KINDS, policy="union", subtractable=True)
    assert s.validate({"deck": None, "voice": True}) == {"deck": None, "voice": True}


def test_user_only_fallback():
    s = user_only_spec("k")
    assert s.scopes == frozenset({"user"}) and s.policy == "override"


def test_registry_get_and_fallback():
    reg = SpecRegistry()
    reg.register(SettingSpec("a", scopes=ALL_KINDS))
    assert reg.get("a").scopes == ALL_KINDS
    assert reg.is_declared("a") and not reg.is_declared("b")
    assert reg.get("b") == user_only_spec("b")
    assert SpecRegistry(fallback=everywhere).get("b") == everywhere("b")
    assert reg.keys() == ["a"]


def test_registry_duplicate_register():
    reg = SpecRegistry()
    reg.register(SettingSpec("a"))
    with pytest.raises(ValueError):
        reg.register(SettingSpec("a"))
    reg.register(SettingSpec("a", label="new"), replace=True)
    assert reg.get("a").label == "new"


def test_apply_overrides():
    reg = SpecRegistry(fallback=everywhere)
    reg.apply_overrides({
        "voice.wake_word": {"operator_writable": True, "scopes": ["branch", "user"]},
    })
    s = reg.get("voice.wake_word")
    assert s.operator_writable and s.scopes == frozenset({"branch", "user"})
    assert reg.is_declared("voice.wake_word")


@pytest.mark.parametrize(
    "fields",
    [{"type": str}, {"policy": "union"}, {"default": 1}, {"key": "x"}, {"colour": "red"},
     {"write_role": "superuser"}],
)
def test_apply_overrides_rejects_disallowed_or_invalid(fields):
    reg = SpecRegistry(fallback=everywhere)
    with pytest.raises(ValueError):
        reg.apply_overrides({"k": fields})


def test_core_registry_has_plugins_enabled():
    reg = core_registry()
    s = reg.get("plugins.enabled")
    assert s in CORE_SPECS
    assert s.policy == "union" and s.subtractable and s.lockable
    assert s.scopes == ALL_KINDS


def test_spec_dict_round_trip():
    s = SettingSpec(
        "voice.wake_word", type=str, default="hey", scopes={"branch", "user"},
        write_role={"branch": "admin"}, label="Wake word", page="voice",
        restart_required=True,
    )
    d = spec_to_dict(s)
    json.dumps(d)  # must be JSON-serializable
    assert d["type"] == "str" and d["scopes"] == ["branch", "user"]
    assert spec_from_dict(d) == s


def test_spec_dict_round_trip_union_and_list_type():
    s = SettingSpec("tags", type=list[str], scopes=ALL_KINDS)
    assert spec_from_dict(spec_to_dict(s)) == s
    assert spec_from_dict(spec_to_dict(CORE_SPECS[0])) == CORE_SPECS[0]


def test_unknown_type_serializes_as_any():
    class Model(BaseModel):
        x: int

    d = spec_to_dict(SettingSpec("m", type=Model))
    assert d["type"] == "any"
    assert spec_from_dict(d).type is object


def test_spec_from_dict_defaults_missing_fields():
    s = spec_from_dict({"key": "k"})
    assert s == SettingSpec("k")


@pytest.mark.parametrize(
    "d",
    [{"key": "a", "type": "complex"}, {"key": "a", "colour": "red"},
     {"key": "a", "default": object()}, {"key": "a", "scopes": ["galaxy"]}, {"type": "str"},
     {"key": "a", "operator_writable": "false"}, {"key": "a", "lockable": 0},
     {"key": "a", "type": ["x"]}, {"key": "a", "scopes": 5},
     {"key": "a", "write_role": ["admin"]}, {"key": "a", "write_role": {"beamline": ["a"]}},
     {"key": "a", "policy": []}, {"key": "a", "label": 5}, {"key": 5}, 5, ["key"]],
)
def test_spec_from_dict_rejects(d):
    with pytest.raises(ValueError):
        spec_from_dict(d)


@pytest.mark.parametrize(
    ("tp", "bad"), [(int, "5"), (bool, "yes"), (str, 5), (list[str], "a,b"), (int, True)]
)
def test_validation_is_strict(tp, bad):
    with pytest.raises(ValueError):
        SettingSpec("k", type=tp).validate(bad)


def test_strict_float_still_accepts_int():
    assert SettingSpec("k", type=float).validate(1) == 1.0


def test_overridable_fields_is_public():
    from lightfall_settings import OVERRIDABLE_FIELDS
    assert "operator_writable" in OVERRIDABLE_FIELDS and "type" not in OVERRIDABLE_FIELDS


@pytest.mark.parametrize("field", ["subtractable", "operator_writable", "lockable",
                                   "restart_required"])
def test_bool_fields_must_be_bool(field):
    with pytest.raises(ValueError):
        SettingSpec("k", scopes=ALL_KINDS, **{field: "false"})
