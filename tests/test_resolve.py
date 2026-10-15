import pytest

from lightfall_settings.resolve import Lock, ScopeSnapshot, resolve
from lightfall_settings.scopes import ALL_KINDS, FACILITY, ScopeId
from lightfall_settings.spec import SettingSpec

BL = ScopeId("beamline", "7.0.1")
BR = ScopeId("branch", "7.0.1.1")
USER = ScopeId("user", "alice")
LOCK = Lock(locked_by="ron", reason="safety")

URL = SettingSpec("tiled.url", type=str, scopes=ALL_KINDS)
PLUGINS = SettingSpec("plugins.enabled", type=bool, scopes=ALL_KINDS, policy="union",
                      subtractable=True)
PLUGINS_FIXED = SettingSpec("plugins.enabled", type=bool, scopes=ALL_KINDS, policy="union")


def snap(scope, settings=None, locks=None):
    return ScopeSnapshot(scope, settings or {}, locks or {})


def test_no_values_gives_default():
    r = resolve(SettingSpec("t", type=str, default="dark", scopes=ALL_KINDS),
                [snap(FACILITY), snap(USER)])
    assert r.value == "dark" and r.origin is None and r.lock is None


def test_override_most_specific_wins():
    r = resolve(URL, [snap(FACILITY, {"tiled.url": "a"}), snap(BL, {"tiled.url": "b"}),
                      snap(BR), snap(USER, {"tiled.url": "c"})])
    assert r.value == "c" and r.origin == USER
    assert r.per_scope == {FACILITY: "a", BL: "b", USER: "c"}


def test_value_at_disallowed_scope_ignored():
    spec = SettingSpec("auth.url", type=str, scopes={"facility"})
    r = resolve(spec, [snap(FACILITY, {"auth.url": "kc"}), snap(USER, {"auth.url": "evil"})])
    assert r.value == "kc" and r.origin == FACILITY


def test_lock_freezes_everything_below():
    r = resolve(URL, [snap(FACILITY, {"tiled.url": "a"}),
                      snap(BL, {"tiled.url": "b"}, {"tiled.url": LOCK}),
                      snap(BR, {"tiled.url": "x"}), snap(USER, {"tiled.url": "y"})])
    assert r.value == "b" and r.origin == BL
    assert r.locked_at == BL and r.lock == LOCK
    assert BR not in r.per_scope and USER not in r.per_scope


def test_lock_without_row_freezes_inherited_value():
    r = resolve(URL, [snap(FACILITY, {"tiled.url": "a"}),
                      snap(BL, {}, {"tiled.url": LOCK}),
                      snap(USER, {"tiled.url": "y"})])
    assert r.value == "a" and r.origin == FACILITY and r.locked_at == BL


def test_lock_at_disallowed_scope_still_freezes():
    spec = SettingSpec("k", type=str, scopes={"facility", "user"})
    r = resolve(spec, [snap(FACILITY, {"k": "a"}), snap(BL, {}, {"k": LOCK}),
                       snap(USER, {"k": "y"})])
    assert r.value == "a" and r.locked_at == BL


def test_invalid_value_falls_back_to_broader():
    r = resolve(URL, [snap(BL, {"tiled.url": "b"}), snap(USER, {"tiled.url": 42})])
    assert r.value == "b" and r.origin == BL and r.rejected == (USER,)


def test_union_merge_and_shadowing():
    r = resolve(PLUGINS, [snap(FACILITY, {"plugins.enabled": {"deck": True, "voice": True}}),
                          snap(BR, {"plugins.enabled": {"voice": False, "vibe": True}})])
    assert r.value == {"deck": True, "voice": False, "vibe": True}
    assert r.item_origins == {"deck": FACILITY, "voice": BR, "vibe": BR}
    assert r.origin == BR


def test_union_tombstone_removes_inherited_item():
    r = resolve(PLUGINS, [snap(FACILITY, {"plugins.enabled": {"deck": True, "voice": True}}),
                          snap(USER, {"plugins.enabled": {"deck": None}})])
    assert r.value == {"voice": True}
    assert "deck" not in r.item_origins


def test_union_tombstone_not_subtractable_rejects_that_scope_only():
    r = resolve(PLUGINS_FIXED, [snap(FACILITY, {"plugins.enabled": {"deck": True}}),
                                snap(USER, {"plugins.enabled": {"deck": None, "x": True}})])
    assert r.value == {"deck": True} and r.rejected == (USER,)


def test_union_non_dict_value_is_rejected_not_crash():
    r = resolve(PLUGINS, [snap(FACILITY, {"plugins.enabled": ["deck"]}),
                          snap(USER, {"plugins.enabled": {"voice": True}})])
    assert r.value == {"voice": True} and r.rejected == (FACILITY,)


def test_union_lock_stops_lower_changes():
    r = resolve(PLUGINS, [snap(BR, {"plugins.enabled": {"deck": True}},
                               {"plugins.enabled": LOCK}),
                          snap(USER, {"plugins.enabled": {"deck": None}})])
    assert r.value == {"deck": True} and r.locked_at == BR


def test_union_default_is_copied_not_mutated():
    default = {"deck": True}
    spec = SettingSpec("p", type=bool, scopes=ALL_KINDS, policy="union", default=default)
    r = resolve(spec, [snap(USER, {"p": {"voice": True}})])
    assert r.value == {"deck": True, "voice": True}
    assert default == {"deck": True}


def test_union_without_default_starts_empty():
    assert resolve(PLUGINS, [snap(FACILITY)]).value == {}


def test_out_of_order_snapshots_rejected():
    with pytest.raises(ValueError):
        resolve(URL, [snap(USER), snap(FACILITY)])
