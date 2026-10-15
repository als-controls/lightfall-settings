import pytest

from lightfall_settings.scopes import FACILITY, ScopeChain, ScopeId


@pytest.mark.parametrize(
    "text",
    ["facility", "beamline:7.0.1", "branch:7.0.1.1",
     "user:3f2a9c1e-77aa-4c1b-9d1e-0a1b2c3d4e5f"],
)
def test_parse_round_trip(text):
    assert str(ScopeId.parse(text)) == text


@pytest.mark.parametrize(
    "bad",
    ["", "facility:als", "beamline:", "bogus:x", "branch:a b", "beamline:a/b",
     "user:x:y", "beamline:_all", "branch:_all", "beamline:..", "user:.", "branch:..."],
)
def test_parse_rejects_bad(bad):
    with pytest.raises(ValueError):
        ScopeId.parse(bad)


def test_scope_ids_are_hashable_and_equal_by_value():
    assert ScopeId("beamline", "7.0.1") == ScopeId.parse("beamline:7.0.1")
    assert len({ScopeId("beamline", "7.0.1"), ScopeId.parse("beamline:7.0.1")}) == 1
    assert ScopeId.parse("facility") == FACILITY


def test_full_chain_accessors():
    chain = ScopeChain.of("facility", "beamline:7.0.1", "branch:7.0.1.1", "user:alice")
    assert len(chain) == 4
    assert chain.beamline == ScopeId("beamline", "7.0.1")
    assert chain.branch == ScopeId("branch", "7.0.1.1")
    assert chain.user == ScopeId("user", "alice")
    assert ScopeId("branch", "7.0.1.1") in chain
    assert chain.above(ScopeId("branch", "7.0.1.1")) == (FACILITY, ScopeId("beamline", "7.0.1"))
    assert chain.above(FACILITY) == ()


@pytest.mark.parametrize(
    "items",
    [("facility",), ("facility", "user:alice"), ("facility", "beamline:8.3.2", "user:alice"),
     ("facility", "beamline:7.0.1", "branch:7.0.1.1")],
)
def test_short_chains_are_valid(items):
    assert len(ScopeChain.of(*items)) == len(items)


@pytest.mark.parametrize(
    "items",
    [(), ("beamline:7.0.1",), ("facility", "branch:x", "beamline:y"),
     ("facility", "beamline:a", "beamline:b"), ("facility", "user:a", "branch:b"),
     ("facility", "branch:7.0.1.1"), ("facility", "branch:7.0.1.1", "user:a")],
)
def test_bad_chains_rejected(items):
    with pytest.raises(ValueError):
        ScopeChain.of(*items)


def test_above_rejects_scope_not_in_chain():
    chain = ScopeChain.of("facility", "beamline:7.0.1")
    with pytest.raises(ValueError):
        chain.above(ScopeId("beamline", "8.3.2"))


def test_with_user_appends_or_replaces():
    chain = ScopeChain.of("facility", "beamline:7.0.1", "branch:7.0.1.1")
    with_alice = chain.with_user("alice")
    assert with_alice.user == ScopeId("user", "alice")
    assert with_alice.with_user("bob").user == ScopeId("user", "bob")
    assert len(with_alice.with_user("bob")) == 4
