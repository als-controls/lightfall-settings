# lightfall-settings

Pure-Python model for Lightfall's scoped settings, shared by the Lightfall client and the
logbook server so both compute identical answers.

- **Scopes**: `facility` → `beamline:<bl>` → `branch:<branch>` → `user:<sub>`, ordered broad to
  specific in a `ScopeChain`.
- **Scope roles** from Keycloak group paths (`/beamlines/<bl>/<role>`,
  `/beamlines/<bl>/branch/<branch>/<role>`, `/beamlines/_all/<role>`, `/BCG_staff`).
- **`SettingSpec`**: which scopes a key may be set at, `override` or `union` policy, write role,
  lockability. Specs serialize to JSON for server-side key proposals and approvals.
- **Resolver**: effective value of a key across a chain of scope snapshots, honouring locks.
- **Write rules**: the server-side checks for set / delete / lock / unlock / publish.

No Qt, no HTTP. Depends only on pydantic.

## Development

    ../lightfall/.venv/Scripts/python -m pytest
    ../lightfall/.venv/Scripts/python -m ruff check .
