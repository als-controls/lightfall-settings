import pytest

from lightfall_settings.resolve import Lock, ScopeSnapshot
from lightfall_settings.rules import WriteDenied, check_publish, check_write
from lightfall_settings.scopes import ALL_KINDS, FACILITY, ScopeChain, ScopeId
from lightfall_settings.spec import SettingSpec

CHAIN = ScopeChain.of("facility", "beamline:7.0.1", "branch:7.0.1.1", "user:alice")
BL = ScopeId("beamline", "7.0.1")
BR = ScopeId("branch", "7.0.1.1")
ALICE = ScopeId("user", "alice")
URL = SettingSpec("tiled.url", type=str, scopes=ALL_KINDS)
LOCK = Lock(locked_by="ron")

MAINT_BL = ["/beamlines/7.0.1/maintainer"]
ADMIN_BL = ["/beamlines/7.0.1/admin"]
OPER_BL = ["/beamlines/7.0.1/operator"]


def write(target, groups, *, action="set", value="https://t", actor="alice",
          snapshots=(), spec=URL):
    return check_write(spec=spec, target=target, chain=CHAIN, actor=actor, groups=groups,
                       snapshots=list(snapshots), action=action, value=value)


def denied(status, **kwargs):
    target = kwargs.pop("target")
    groups = kwargs.pop("groups")
    with pytest.raises(WriteDenied) as ei:
        write(target, groups, **kwargs)
    assert ei.value.status == status, ei.value.reason


def test_maintainer_sets_beamline_and_gets_validated_value():
    assert write(BL, MAINT_BL) == "https://t"
    assert write(BR, MAINT_BL) == "https://t"


def test_operator_and_viewer_cannot_set():
    denied(403, target=BL, groups=OPER_BL)
    denied(403, target=BL, groups=["/beamlines/7.0.1/viewer"])
    denied(403, target=BL, groups=[])


def test_operator_writable_key():
    spec = SettingSpec("voice.wake_word", type=str, scopes=ALL_KINDS, operator_writable=True)
    assert write(BR, OPER_BL, spec=spec, value="hey") == "hey"


def test_user_scope_only_for_its_owner():
    assert write(ALICE, [], actor="alice") == "https://t"
    denied(403, target=ALICE, groups=["/beamlines/_all/admin"], actor="bob")


def test_key_not_allowed_at_scope_kind_is_409():
    spec = SettingSpec("theme", type=str)  # user only
    denied(409, target=BL, groups=MAINT_BL, spec=spec)


def test_role_checked_before_scope_kind():
    spec = SettingSpec("theme", type=str)
    denied(403, target=BL, groups=["/beamlines/7.0.1/viewer"], spec=spec)


def test_lock_above_blocks_even_admin_at_target():
    snaps = [ScopeSnapshot(BL, {}, {"tiled.url": LOCK}), ScopeSnapshot(BR)]
    denied(423, target=BR, groups=["/beamlines/_all/admin"], snapshots=snaps)
    denied(423, target=ALICE, groups=[], snapshots=snaps)


def test_lock_at_target_blocks_set_and_delete():
    snaps = [ScopeSnapshot(BL, {"tiled.url": "x"}, {"tiled.url": LOCK})]
    denied(423, target=BL, groups=ADMIN_BL, snapshots=snaps)
    denied(423, target=BL, groups=ADMIN_BL, snapshots=snaps, action="delete")


def test_lock_unlock_require_admin():
    denied(403, target=BL, groups=MAINT_BL, action="lock")
    assert write(BL, ADMIN_BL, action="lock") is None
    snaps = [ScopeSnapshot(BL, {}, {"tiled.url": LOCK})]
    assert write(BL, ADMIN_BL, action="unlock", snapshots=snaps) is None
    assert write(BL, ADMIN_BL, action="lock", snapshots=snaps) is None  # re-lock ok


def test_unlock_when_not_locked_is_404():
    denied(404, target=BL, groups=ADMIN_BL, action="unlock")


def test_unlockable_key_and_user_scope_lock_are_409():
    spec = SettingSpec("k", type=str, scopes=ALL_KINDS, lockable=False)
    denied(409, target=BL, groups=ADMIN_BL, action="lock", spec=spec)
    denied(409, target=ALICE, groups=[], action="lock")


def test_bad_value_is_422():
    denied(422, target=BL, groups=MAINT_BL, value=42)


def test_target_not_in_chain_is_404():
    denied(404, target=ScopeId("beamline", "8.3.2"), groups=["/beamlines/_all/admin"])


def test_facility_writers_and_lockers():
    assert write(FACILITY, ["/BCG_staff"]) == "https://t"
    denied(403, target=FACILITY, groups=["/BCG_staff"], action="lock")
    assert write(FACILITY, ["/beamlines/_all/admin"], action="lock") is None
    assert write(FACILITY, ["/beamlines/_all/owner"], action="lock") is None
    denied(403, target=FACILITY, groups=MAINT_BL)


def test_check_publish():
    check_publish(target=BR, chain=CHAIN, actor="alice", groups=MAINT_BL)
    check_publish(target=ALICE, chain=CHAIN, actor="alice", groups=[])
    for target, groups, actor in [(BR, OPER_BL, "alice"), (ALICE, [], "bob"),
                                  (FACILITY, MAINT_BL, "alice")]:
        with pytest.raises(WriteDenied) as ei:
            check_publish(target=target, chain=CHAIN, actor=actor, groups=groups)
        assert ei.value.status == 403
