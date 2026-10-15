"""Resolve a key's effective value across a chain of scope snapshots."""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from lightfall_settings.scopes import KIND_RANK, ScopeId
from lightfall_settings.spec import SettingSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Lock:
    locked_by: str
    reason: str = ""
    locked_at: str = ""  # ISO timestamp, informational


@dataclass(frozen=True)
class ScopeSnapshot:
    scope: ScopeId
    settings: Mapping[str, Any] = field(default_factory=dict)
    locks: Mapping[str, Lock] = field(default_factory=dict)


@dataclass(frozen=True)
class Resolution:
    key: str
    value: Any
    origin: ScopeId | None
    locked_at: ScopeId | None
    lock: Lock | None
    per_scope: Mapping[ScopeId, Any]
    item_origins: Mapping[str, ScopeId]
    rejected: tuple[ScopeId, ...]


def _check_order(snapshots: Sequence[ScopeSnapshot]) -> None:
    ranks = [KIND_RANK[s.scope.kind] for s in snapshots]
    if any(b <= a for a, b in zip(ranks, ranks[1:], strict=False)):
        raise ValueError("snapshots must be ordered broad -> specific")


def resolve(spec: SettingSpec, snapshots: Sequence[ScopeSnapshot]) -> Resolution:
    _check_order(snapshots)
    key = spec.key
    union = spec.policy == "union"
    value: Any = dict(spec.default or {}) if union else spec.default
    origin: ScopeId | None = None
    item_origins: dict[str, ScopeId] = {}
    per_scope: dict[ScopeId, Any] = {}
    rejected: list[ScopeId] = []
    locked_at: ScopeId | None = None
    lock: Lock | None = None

    for snap in snapshots:
        scope = snap.scope
        if key in snap.settings and spec.allows(scope.kind):
            try:
                v = spec.validate(snap.settings[key])
            except ValueError as e:
                rejected.append(scope)
                logger.warning("Ignoring invalid value for %s at %s: %s", key, scope, e)
            else:
                per_scope[scope] = v
                origin = scope
                if not union:
                    value = v
                else:
                    for name, item in v.items():
                        if item is None:
                            value.pop(name, None)
                            item_origins.pop(name, None)
                        else:
                            value[name] = item
                            item_origins[name] = scope
        if key in snap.locks:
            locked_at, lock = scope, snap.locks[key]
            break

    return Resolution(
        key=key,
        value=value,
        origin=origin,
        locked_at=locked_at,
        lock=lock,
        per_scope=per_scope,
        item_origins=item_origins,
        rejected=tuple(rejected),
    )
