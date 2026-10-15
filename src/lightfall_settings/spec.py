"""Setting specifications: where a key may be set, how levels combine, who may write.

Client-declared specs are advisory: they drive the UI and become the proposed
spec of a key proposal. The server enforces the core specs, specs a facility
admin has approved (stored via :func:`spec_to_dict`), and ``user_only_spec``
for anything else.
"""
from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal, get_args

from pydantic import TypeAdapter, ValidationError

from lightfall_settings.roles import ROLE_RANK, ScopeRole
from lightfall_settings.scopes import ALL_KINDS

Policy = Literal["override", "union"]
_POLICIES = frozenset(get_args(Policy))
OVERRIDABLE_FIELDS = frozenset(
    {"scopes", "write_role", "operator_writable", "lockable", "subtractable"}
)


@lru_cache(maxsize=256)
def _adapter_cached(tp: Any) -> TypeAdapter:
    return TypeAdapter(tp)


def _adapter(tp: Any) -> TypeAdapter:
    try:
        return _adapter_cached(tp)
    except TypeError:  # unhashable type expression
        return TypeAdapter(tp)


@dataclass(frozen=True)
class SettingSpec:
    """One setting key's rules. ``operator_writable=True`` takes precedence over
    ``write_role``: operators (and above) may then write it at every allowed scope."""

    key: str
    type: Any = object
    default: Any = None
    scopes: frozenset[str] = field(default_factory=lambda: frozenset({"user"}))
    policy: Policy = "override"
    subtractable: bool = False
    write_role: ScopeRole | Mapping[str, ScopeRole] = "maintainer"
    operator_writable: bool = False
    lockable: bool = True
    label: str = ""
    page: str = ""
    restart_required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("SettingSpec.key must be a non-empty string")
        for name in ("subtractable", "operator_writable", "lockable", "restart_required"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{self.key}: {name} must be true or false")
        for name in ("label", "page"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{self.key}: {name} must be a string")
        if isinstance(self.scopes, str) or not all(isinstance(k, str) for k in self.scopes):
            raise ValueError(f"{self.key}: scopes must be a list of scope kinds")
        if not isinstance(self.write_role, (str, Mapping)) or (
            isinstance(self.write_role, Mapping)
            and not all(isinstance(v, str) for v in self.write_role.values())
        ):
            raise ValueError(f"{self.key}: write_role must be a role or a kind -> role map")
        if not isinstance(self.policy, str):
            raise ValueError(f"{self.key}: policy must be a string")
        scopes = frozenset(self.scopes)
        object.__setattr__(self, "scopes", scopes)
        if not scopes:
            raise ValueError(f"{self.key}: scopes must not be empty")
        if not scopes <= ALL_KINDS:
            raise ValueError(f"{self.key}: unknown scope kinds {sorted(scopes - ALL_KINDS)}")
        if self.policy not in _POLICIES:
            raise ValueError(f"{self.key}: unknown policy {self.policy!r}")
        if self.subtractable and self.policy != "union":
            raise ValueError(f"{self.key}: subtractable requires policy='union'")
        roles = (
            dict(self.write_role)
            if isinstance(self.write_role, Mapping)
            else {"*": self.write_role}
        )
        for kind, role in roles.items():
            if kind != "*" and kind not in ALL_KINDS:
                raise ValueError(f"{self.key}: write_role for unknown scope kind {kind!r}")
            if role not in ROLE_RANK:
                raise ValueError(f"{self.key}: unknown role {role!r}")
            if ROLE_RANK[role] < ROLE_RANK["operator"]:
                raise ValueError(f"{self.key}: write_role {role!r} is below operator")

    def allows(self, kind: str) -> bool:
        return kind in self.scopes

    def required_role(self, kind: str) -> ScopeRole:
        """Minimum scope role to set/delete this key at a non-user scope of ``kind``."""
        if self.operator_writable:
            return "operator"
        if isinstance(self.write_role, Mapping):
            return self.write_role.get(kind, "maintainer")
        return self.write_role

    def _validate_item(self, value: Any) -> Any:
        try:
            return _adapter(self.type).validate_python(value, strict=True)
        except ValidationError as e:
            raise ValueError(f"{self.key}: {e.errors()[0]['msg']}") from None

    def validate(self, value: Any) -> Any:
        """Return the validated value; raise ``ValueError`` if it doesn't fit."""
        if self.policy == "override":
            return self._validate_item(value)
        if not isinstance(value, dict):
            raise ValueError(f"{self.key}: union value must be an object keyed by item name")
        out: dict[str, Any] = {}
        for name, item in value.items():
            if not isinstance(name, str) or not name:
                raise ValueError(f"{self.key}: union item names must be non-empty strings")
            if item is None:
                if not self.subtractable:
                    raise ValueError(f"{self.key}: items cannot be removed at lower scopes")
                out[name] = None
            else:
                out[name] = self._validate_item(item)
        return out


def user_only_spec(key: str) -> SettingSpec:
    """Fallback for undeclared/unapproved keys: today's per-user behavior."""
    return SettingSpec(key=key)


# Type names a spec can carry over the wire. Anything else serializes as "any";
# the declaring client still validates with its own richer type.
TYPE_NAMES: dict[str, Any] = {
    "any": object,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list[str]": list[str],
    "dict": dict,
}
_SPEC_FIELDS = frozenset(f.name for f in dataclasses.fields(SettingSpec))


def type_name(tp: Any) -> str:
    for name, known in TYPE_NAMES.items():
        if known == tp:
            return name
    return "any"


def spec_to_dict(spec: SettingSpec) -> dict[str, Any]:
    write_role = (
        dict(spec.write_role) if isinstance(spec.write_role, Mapping) else spec.write_role
    )
    return {
        "key": spec.key,
        "type": type_name(spec.type),
        "default": spec.default,
        "scopes": sorted(spec.scopes),
        "policy": spec.policy,
        "subtractable": spec.subtractable,
        "write_role": write_role,
        "operator_writable": spec.operator_writable,
        "lockable": spec.lockable,
        "label": spec.label,
        "page": spec.page,
        "restart_required": spec.restart_required,
    }


def spec_from_dict(d: Mapping[str, Any]) -> SettingSpec:
    """Build a spec from untrusted JSON. Raises ``ValueError`` for anything malformed."""
    if not isinstance(d, Mapping):
        raise ValueError("spec must be an object")
    try:
        return _spec_from_dict(d)
    except TypeError as e:  # wrong JSON types (lists, numbers) where scalars belong
        raise ValueError(f"malformed spec: {e}") from None


def _spec_from_dict(d: Mapping[str, Any]) -> SettingSpec:
    bad = set(d) - _SPEC_FIELDS
    if bad:
        raise ValueError(f"unknown spec fields {sorted(bad)}")
    if "key" not in d:
        raise ValueError("spec is missing 'key'")
    data = dict(d)
    tname = data.pop("type", "any")
    if not isinstance(tname, str) or tname not in TYPE_NAMES:
        raise ValueError(f"unknown spec type {tname!r}")
    data["type"] = TYPE_NAMES[tname]
    if "scopes" in data:
        if isinstance(data["scopes"], str):
            raise ValueError("scopes must be a list of scope kinds")
        data["scopes"] = frozenset(data["scopes"])
    try:
        json.dumps(data.get("default"))
    except TypeError:
        raise ValueError("spec default must be JSON-serializable") from None
    return SettingSpec(**data)


class SpecRegistry:
    def __init__(self, fallback: Callable[[str], SettingSpec] = user_only_spec) -> None:
        self._specs: dict[str, SettingSpec] = {}
        self._fallback = fallback

    def register(self, spec: SettingSpec, *, replace: bool = False) -> None:
        if spec.key in self._specs and not replace:
            raise ValueError(f"setting {spec.key!r} is already registered")
        self._specs[spec.key] = spec

    def register_all(self, specs: Iterable[SettingSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def get(self, key: str) -> SettingSpec:
        spec = self._specs.get(key)
        return spec if spec is not None else self._fallback(key)

    def is_declared(self, key: str) -> bool:
        return key in self._specs

    def keys(self) -> list[str]:
        return sorted(self._specs)

    def apply_overrides(self, overrides: Mapping[str, Mapping[str, Any]]) -> None:
        """Loosen or restrict rule fields of keys (admin edits before approving)."""
        for key, fields in overrides.items():
            bad = set(fields) - OVERRIDABLE_FIELDS
            if bad:
                raise ValueError(f"{key}: fields {sorted(bad)} cannot be overridden")
            changes = dict(fields)
            if "scopes" in changes:
                changes["scopes"] = frozenset(changes["scopes"])
            self._specs[key] = dataclasses.replace(self.get(key), **changes)


CORE_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec(
        key="plugins.enabled",
        type=bool,
        scopes=ALL_KINDS,
        policy="union",
        subtractable=True,
        lockable=True,
        label="Enabled plugins",
        page="plugins",
    ),
)


def core_registry(fallback: Callable[[str], SettingSpec] = user_only_spec) -> SpecRegistry:
    reg = SpecRegistry(fallback=fallback)
    reg.register_all(CORE_SPECS)
    return reg
