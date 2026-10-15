"""Scope roles derived from Keycloak group paths.

Group tree (full paths, as emitted by Keycloak's Group Membership mapper)::

    /beamlines/<bl>/<role>                      role on beamline <bl> and its branches
    /beamlines/<bl>/branch/<branch>/<role>      role on that branch only
    /beamlines/_all/<role>                      role on every beamline and branch

Facility roles come from an explicit map (``DEFAULT_FACILITY_GRANTS``).
User scopes never get a group role: only the user writes their own scope.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal, get_args

from lightfall_settings.scopes import ScopeChain, ScopeId

ScopeRole = Literal["viewer", "operator", "maintainer", "admin", "owner"]
ROLE_RANK: dict[str, int] = {
    "viewer": 1, "operator": 2, "maintainer": 3, "admin": 4, "owner": 4,
}
_ROLES = frozenset(get_args(ScopeRole))
_ALL = "_all"

DEFAULT_FACILITY_GRANTS: Mapping[str, ScopeRole] = {
    "/beamlines/_all/admin": "admin",
    "/beamlines/_all/owner": "owner",
    "/BCG_staff": "maintainer",
}


def normalize_group(path: str) -> str:
    """``" beamlines/x/admin/ "`` -> ``"/beamlines/x/admin"``; empty stays empty."""
    stripped = path.strip().strip("/")
    return f"/{stripped}" if stripped else ""


def role_at_least(role: ScopeRole | None, needed: ScopeRole) -> bool:
    return role is not None and ROLE_RANK[role] >= ROLE_RANK[needed]


def _max_role(a: ScopeRole | None, b: ScopeRole) -> ScopeRole:
    return b if a is None or ROLE_RANK[b] > ROLE_RANK[a] else a


def _beamline_grant(parts: list[str], scope: ScopeId, parent_bl: str | None) -> ScopeRole | None:
    """Role granted on a beamline/branch ``scope`` by one ``/beamlines/...`` path."""
    if len(parts) == 3:  # beamlines/<bl>/<role>
        _, bl, role = parts
        if role not in _ROLES:
            return None
        target_bl = scope.name if scope.kind == "beamline" else parent_bl
        if bl == _ALL or (target_bl is not None and bl == target_bl):
            return role  # type: ignore[return-value]
        return None
    if len(parts) == 5 and parts[2] == "branch":  # beamlines/<bl>/branch/<br>/<role>
        _, bl, _, br, role = parts
        if role not in _ROLES or scope.kind != "branch" or br != scope.name:
            return None
        if parent_bl is None or bl in (parent_bl, _ALL):
            return role  # type: ignore[return-value]
    return None


def role_on(
    scope: ScopeId,
    chain: ScopeChain,
    groups: Iterable[str],
    facility_grants: Mapping[str, ScopeRole] = DEFAULT_FACILITY_GRANTS,
) -> ScopeRole | None:
    """Highest scope role ``groups`` confer on ``scope`` (``None`` if none)."""
    if scope.kind == "user":
        return None
    normalized = [normalize_group(g) for g in groups]
    best: ScopeRole | None = None
    if scope.kind == "facility":
        grants = {normalize_group(k): v for k, v in facility_grants.items()}
        for g in normalized:
            if g in grants:
                best = _max_role(best, grants[g])
        return best
    parent = chain.beamline
    parent_bl = parent.name if parent is not None else None
    for g in normalized:
        parts = g.strip("/").split("/")
        if not parts or parts[0] != "beamlines":
            continue
        role = _beamline_grant(parts, scope, parent_bl)
        if role is not None:
            best = _max_role(best, role)
    return best


def roles_for_chain(
    chain: ScopeChain,
    groups: Iterable[str],
    facility_grants: Mapping[str, ScopeRole] = DEFAULT_FACILITY_GRANTS,
) -> dict[ScopeId, ScopeRole | None]:
    groups = list(groups)
    return {s: role_on(s, chain, groups, facility_grants) for s in chain}
