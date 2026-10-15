"""Server-side write checks for scoped settings and content.

Check order (each failure raises :class:`WriteDenied` with an HTTP status):
scope in chain (404) -> role (403) -> key allowed at scope kind / lockable (409)
-> locks (423) -> value (422).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from lightfall_settings.resolve import ScopeSnapshot
from lightfall_settings.roles import (
    DEFAULT_FACILITY_GRANTS,
    ScopeRole,
    role_at_least,
    role_on,
)
from lightfall_settings.scopes import ScopeChain, ScopeId
from lightfall_settings.spec import SettingSpec

Action = Literal["set", "delete", "lock", "unlock"]


class WriteDenied(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(f"{status}: {reason}")
        self.status = status
        self.reason = reason


def _require_role(
    target: ScopeId,
    chain: ScopeChain,
    actor: str,
    groups: Iterable[str],
    needed: ScopeRole,
    facility_grants: Mapping[str, ScopeRole],
) -> None:
    if target.kind == "user":
        if target.name != actor:
            raise WriteDenied(403, "only the user may write their own scope")
        return
    role = role_on(target, chain, groups, facility_grants)
    if not role_at_least(role, needed):
        raise WriteDenied(403, f"{needed} role required on {target} (have {role or 'none'})")


def check_write(
    *,
    spec: SettingSpec,
    target: ScopeId,
    chain: ScopeChain,
    actor: str,
    groups: Iterable[str],
    snapshots: Sequence[ScopeSnapshot],
    action: Action,
    value: Any = None,
    facility_grants: Mapping[str, ScopeRole] = DEFAULT_FACILITY_GRANTS,
) -> Any:
    """Check one write. ``snapshots`` must include every scope in ``chain`` that
    has data for ``spec.key`` (in practice: load all of them) -- a lock in a scope
    missing from ``snapshots`` is invisible here. Returns the validated value
    for ``set``."""
    if target not in chain:
        raise WriteDenied(404, f"{target} is not in the session's scope chain")

    is_lock_action = action in ("lock", "unlock")
    if is_lock_action and target.kind == "user":
        raise WriteDenied(409, "user scope cannot be locked")
    needed: ScopeRole = "admin" if is_lock_action else spec.required_role(target.kind)
    _require_role(target, chain, actor, list(groups), needed, facility_grants)

    if not spec.allows(target.kind):
        raise WriteDenied(409, f"{spec.key} cannot be set at {target.kind} scope")
    if is_lock_action and not spec.lockable:
        raise WriteDenied(409, f"{spec.key} is not lockable")

    above = set(chain.above(target))
    target_locked = False
    for snap in snapshots:
        if spec.key not in snap.locks:
            continue
        if snap.scope in above:
            raise WriteDenied(423, f"{spec.key} is locked at {snap.scope}")
        if snap.scope == target:
            target_locked = True
    if target_locked and action in ("set", "delete"):
        raise WriteDenied(423, f"{spec.key} is locked at {target}; unlock it first")
    if action == "unlock" and not target_locked:
        raise WriteDenied(404, f"{spec.key} is not locked at {target}")

    if action == "set":
        try:
            return spec.validate(value)
        except ValueError as e:
            raise WriteDenied(422, str(e)) from None
    return None


def check_publish(
    *,
    target: ScopeId,
    chain: ScopeChain,
    actor: str,
    groups: Iterable[str],
    facility_grants: Mapping[str, ScopeRole] = DEFAULT_FACILITY_GRANTS,
) -> None:
    """Publish/retract content at ``target``: maintainer there, or the user's own scope."""
    if target not in chain:
        raise WriteDenied(404, f"{target} is not in the session's scope chain")
    _require_role(target, chain, actor, list(groups), "maintainer", facility_grants)
