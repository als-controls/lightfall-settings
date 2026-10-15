import pytest

from lightfall_settings.roles import (
    ROLE_RANK,
    normalize_group,
    role_at_least,
    role_on,
    roles_for_chain,
    validate_facility_grants,
)
from lightfall_settings.scopes import FACILITY, ScopeChain, ScopeId

CHAIN = ScopeChain.of("facility", "beamline:7.0.1", "branch:7.0.1.1", "user:alice")
BL = ScopeId("beamline", "7.0.1")
BR = ScopeId("branch", "7.0.1.1")
USER = ScopeId("user", "alice")


@pytest.mark.parametrize(
    ("groups", "facility", "beamline", "branch"),
    [
        ([], None, None, None),
        (["/beamlines/7.0.1/maintainer"], None, "maintainer", "maintainer"),
        (["/beamlines/7.0.1/branch/7.0.1.1/operator"], None, None, "operator"),
        (["/beamlines/7.0.1/branch/7.0.1.2/admin"], None, None, None),
        (["/beamlines/7.0.10/admin"], None, None, None),
        (["/beamlines/7.0/admin"], None, None, None),
        (["/beamlines/_all/viewer"], None, "viewer", "viewer"),
        (["/beamlines/_all/admin"], "admin", "admin", "admin"),
        (["/beamlines/_all/owner"], "owner", "owner", "owner"),
        (["/BCG_staff"], "maintainer", None, None),
        (["beamlines/7.0.1/maintainer/"], None, "maintainer", "maintainer"),
        (["  /beamlines/7.0.1/viewer  "], None, "viewer", "viewer"),
        (["/beamlines/7.0.1/viewer", "/beamlines/7.0.1/branch/7.0.1.1/admin"],
         None, "viewer", "admin"),
        (["/beamlines/7.0.1/branch"], None, None, None),
        (["/beamlines/7.0.1/superuser"], None, None, None),
        (["/beamlines/8.3.2/branch/7.0.1.1/admin"], None, None, None),
        (["/other/7.0.1/admin"], None, None, None),
    ],
)
def test_role_on(groups, facility, beamline, branch):
    assert role_on(FACILITY, CHAIN, groups) == facility
    assert role_on(BL, CHAIN, groups) == beamline
    assert role_on(BR, CHAIN, groups) == branch


def test_user_scope_never_gets_a_group_role():
    assert role_on(USER, CHAIN, ["/beamlines/_all/admin", "/BCG_staff"]) is None


def test_custom_facility_grants():
    grants = {"/lightfall_facility_admin": "admin"}
    assert role_on(FACILITY, CHAIN, ["/lightfall_facility_admin"], grants) == "admin"
    assert role_on(FACILITY, CHAIN, ["/BCG_staff"], grants) is None


def test_facility_grant_keys_are_normalized():
    assert role_on(FACILITY, CHAIN, ["/BCG_staff"], {"BCG_staff/": "maintainer"}) == "maintainer"


def test_roles_for_chain():
    roles = roles_for_chain(CHAIN, ["/beamlines/7.0.1/operator"])
    assert roles == {FACILITY: None, BL: "operator", BR: "operator", USER: None}


def test_role_ranking():
    assert ROLE_RANK["admin"] == ROLE_RANK["owner"]
    assert role_at_least("owner", "admin")
    assert role_at_least("maintainer", "operator")
    assert not role_at_least("viewer", "operator")
    assert not role_at_least(None, "viewer")


def test_normalize_group():
    assert normalize_group(" beamlines/7.0.1/admin/ ") == "/beamlines/7.0.1/admin"
    assert normalize_group("/") == ""


def test_non_string_groups_are_ignored():
    assert role_on(BL, CHAIN, [None, 5, "/beamlines/7.0.1/viewer"]) == "viewer"
    assert normalize_group(None) == ""


def test_bad_facility_grant_values_are_ignored_by_role_on():
    assert role_on(FACILITY, CHAIN, ["/x"], {"/x": "superuser"}) is None


def test_validate_facility_grants():
    assert validate_facility_grants({"BCG_staff/": "maintainer"}) == {"/BCG_staff": "maintainer"}
    with pytest.raises(ValueError):
        validate_facility_grants({"/x": "superuser"})
    with pytest.raises(ValueError):
        validate_facility_grants({"": "admin"})
