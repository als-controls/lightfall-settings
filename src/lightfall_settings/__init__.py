"""Scoped settings model shared by the Lightfall client and server."""
from lightfall_settings.resolve import Lock, Resolution, ScopeSnapshot, resolve
from lightfall_settings.roles import (
    DEFAULT_FACILITY_GRANTS,
    ROLE_RANK,
    ScopeRole,
    role_at_least,
    role_on,
    roles_for_chain,
    validate_facility_grants,
)
from lightfall_settings.rules import Action, WriteDenied, check_publish, check_write
from lightfall_settings.scopes import ALL_KINDS, FACILITY, ScopeChain, ScopeId, ScopeKind
from lightfall_settings.spec import (
    CORE_SPECS,
    OVERRIDABLE_FIELDS,
    SECRET_MARKERS,
    TYPE_NAMES,
    SettingSpec,
    SpecRegistry,
    core_registry,
    spec_from_dict,
    spec_to_dict,
    type_name,
    user_only_spec,
)

__all__ = [
    "ALL_KINDS", "CORE_SPECS", "DEFAULT_FACILITY_GRANTS", "FACILITY", "OVERRIDABLE_FIELDS",
    "ROLE_RANK", "SECRET_MARKERS", "TYPE_NAMES", "Action", "Lock", "Resolution", "ScopeChain",
    "ScopeId", "ScopeKind", "ScopeRole", "ScopeSnapshot", "SettingSpec", "SpecRegistry",
    "WriteDenied", "check_publish", "check_write", "core_registry", "resolve", "role_at_least",
    "role_on", "roles_for_chain", "spec_from_dict", "spec_to_dict", "type_name", "user_only_spec",
    "validate_facility_grants",
]
