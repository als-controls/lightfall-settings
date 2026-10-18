"""SettingSpec.public: facility values served without auth in /.well-known/lightfall."""
import pytest

from lightfall_settings import (
    SECRET_MARKERS,
    SettingSpec,
    core_registry,
    spec_from_dict,
    spec_to_dict,
)
from lightfall_settings.scopes import ALL_KINDS

NEW_FACILITY_KEYS = (
    "auth.provider", "auth.server_url", "auth.realm", "auth.client_id",
    "facility.proxy_domains", "agent.backend", "agent.agy_gcp_project",
    "agent.agy_gcp_location",
)
SERVICE_KEYS = ("tiled_url", "logbook_url", "ipc_nats_url")


def test_public_defaults_false():
    assert SettingSpec("theme").public is False


def test_public_must_be_bool():
    with pytest.raises(ValueError):
        SettingSpec("k", public="yes")


def test_secret_markers_are_exact():
    assert SECRET_MARKERS == ("api_key", "token", "secret", "password")


@pytest.mark.parametrize(
    "key", ["claude_api_key", "auth.token_url", "OIDC_SECRET", "db.password", "tiled.api_key"]
)
def test_secret_like_keys_cannot_be_public(key):
    with pytest.raises(ValueError, match="secret"):
        SettingSpec(key, scopes={"facility"}, public=True)


def test_secret_like_key_may_exist_when_not_public():
    assert SettingSpec("auth.client_secret", scopes={"facility"}).public is False


@pytest.mark.parametrize("key", NEW_FACILITY_KEYS)
def test_new_core_specs_are_facility_only_and_public(key):
    reg = core_registry()
    assert reg.is_declared(key)
    spec = reg.get(key)
    assert spec.scopes == frozenset({"facility"})
    assert spec.public is True


@pytest.mark.parametrize("key", SERVICE_KEYS)
def test_service_url_specs_are_public_and_facility_capable(key):
    reg = core_registry()
    assert reg.is_declared(key)
    spec = reg.get(key)
    assert spec.public is True
    assert spec.scopes == ALL_KINDS
    assert spec.type is str


def test_proxy_domains_is_a_string_list():
    spec = core_registry().get("facility.proxy_domains")
    assert spec.type == list[str]
    assert spec.validate(["*.lbl.gov"]) == ["*.lbl.gov"]
    with pytest.raises(ValueError):
        spec.validate("*.lbl.gov")


def test_plugins_enabled_is_still_first_and_private():
    from lightfall_settings import CORE_SPECS
    assert CORE_SPECS[0].key == "plugins.enabled"
    assert CORE_SPECS[0].public is False


def test_public_round_trips_through_dict():
    s = SettingSpec("auth.realm", type=str, scopes={"facility"}, public=True)
    d = spec_to_dict(s)
    assert d["public"] is True
    assert spec_from_dict(d) == s


def test_spec_from_dict_rejects_a_public_secret():
    with pytest.raises(ValueError):
        spec_from_dict({"key": "x_token", "public": True})


def test_spec_from_dict_without_public_defaults_false():
    assert spec_from_dict({"key": "k"}).public is False
