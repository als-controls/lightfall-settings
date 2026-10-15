"""Scope identifiers and chains.

A scope is where a setting value or content item lives. A chain lists the
scopes that apply to one session, ordered broad -> specific:
``facility`` -> ``beamline:<bl>`` -> ``branch:<branch>`` -> ``user:<sub>``.
Shorter chains are valid (a beamline without branches, an unbound workstation).
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, get_args

ScopeKind = Literal["facility", "beamline", "branch", "user"]
KIND_RANK: dict[str, int] = {"facility": 0, "beamline": 1, "branch": 2, "user": 3}
ALL_KINDS: frozenset[str] = frozenset(get_args(ScopeKind))

# Beamline/branch names like 7.0.1.1, Keycloak subs (UUIDs), plain usernames.
_NAME_RE = re.compile(r"^[A-Za-z0-9._@-]+$")
# "_all" is the Keycloak group meaning "every beamline"; never a real scope.
_RESERVED_NAMES = frozenset({"_all"})


@dataclass(frozen=True)
class ScopeId:
    kind: ScopeKind
    name: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ALL_KINDS:
            raise ValueError(f"unknown scope kind {self.kind!r}")
        if self.kind == "facility":
            if self.name:
                raise ValueError("the facility scope has no name")
            return
        if not self.name or not _NAME_RE.match(self.name):
            raise ValueError(f"invalid {self.kind} scope name {self.name!r}")
        if self.name in _RESERVED_NAMES:
            raise ValueError(f"{self.name!r} is reserved and cannot name a scope")

    def __str__(self) -> str:
        return "facility" if self.kind == "facility" else f"{self.kind}:{self.name}"

    @classmethod
    def parse(cls, text: str) -> ScopeId:
        if text == "facility":
            return cls("facility")
        kind, sep, name = text.partition(":")
        if not sep or kind == "facility":
            raise ValueError(f"invalid scope id {text!r}")
        return cls(kind, name)  # type: ignore[arg-type]


FACILITY = ScopeId("facility")


def _as_scope(item: str | ScopeId) -> ScopeId:
    return item if isinstance(item, ScopeId) else ScopeId.parse(item)


@dataclass(frozen=True)
class ScopeChain:
    scopes: tuple[ScopeId, ...]

    def __post_init__(self) -> None:
        if not self.scopes or self.scopes[0] != FACILITY:
            raise ValueError("a scope chain must start with the facility scope")
        ranks = [KIND_RANK[s.kind] for s in self.scopes]
        if any(b <= a for a, b in zip(ranks, ranks[1:], strict=False)):
            raise ValueError(
                "scope chain must be strictly broad -> specific: "
                + ", ".join(str(s) for s in self.scopes)
            )

    @classmethod
    def of(cls, *items: str | ScopeId) -> ScopeChain:
        return cls(tuple(_as_scope(i) for i in items))

    def __iter__(self) -> Iterator[ScopeId]:
        return iter(self.scopes)

    def __len__(self) -> int:
        return len(self.scopes)

    def __contains__(self, scope: object) -> bool:
        return scope in self.scopes

    def _of_kind(self, kind: str) -> ScopeId | None:
        return next((s for s in self.scopes if s.kind == kind), None)

    @property
    def beamline(self) -> ScopeId | None:
        return self._of_kind("beamline")

    @property
    def branch(self) -> ScopeId | None:
        return self._of_kind("branch")

    @property
    def user(self) -> ScopeId | None:
        return self._of_kind("user")

    def above(self, scope: ScopeId) -> tuple[ScopeId, ...]:
        """Scopes strictly broader than ``scope`` in this chain."""
        try:
            idx = self.scopes.index(scope)
        except ValueError:
            raise ValueError(f"{scope} is not in this chain") from None
        return self.scopes[:idx]

    def with_user(self, sub: str) -> ScopeChain:
        base = tuple(s for s in self.scopes if s.kind != "user")
        return ScopeChain(base + (ScopeId("user", sub),))
