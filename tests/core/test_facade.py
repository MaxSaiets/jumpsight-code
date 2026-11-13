"""Package facade: patches on the package reach the owning submodule and undo cleanly."""

from __future__ import annotations

import sys
import types

import pytest

from jumpsight_core.facade import install_facade


@pytest.fixture
def package():
    owner = types.ModuleType("fake_pkg.state")
    owner.WORK = "original"
    pkg = types.ModuleType("fake_pkg")
    sys.modules["fake_pkg"] = pkg
    install_facade("fake_pkg", owned={"WORK": owner})
    yield pkg, owner
    del sys.modules["fake_pkg"]


def test_owned_name_is_visible_in_the_package_dict(package):
    pkg, _owner = package
    assert "WORK" in vars(pkg)


def test_write_reaches_owner_and_read_follows_owner(package):
    pkg, owner = package
    pkg.WORK = "patched"
    assert owner.WORK == "patched"
    owner.WORK = "changed by owner"
    assert pkg.WORK == "changed by owner"


def test_undo_as_pytest_does_it_restores_instead_of_deleting(package):
    """pytest >= 9.2 reads the old value from `vars(target)` and deletes the name when absent."""
    pkg, owner = package
    old = vars(pkg).get("WORK", None)
    pkg.WORK = "patched"
    if old is None:
        delattr(pkg, "WORK")
    else:
        pkg.WORK = old
    assert owner.WORK == "original"


def test_monkeypatch_round_trip(package, monkeypatch):
    pkg, owner = package
    with monkeypatch.context() as m:
        m.setattr(pkg, "WORK", "patched")
        assert owner.WORK == "patched"
    assert owner.WORK == "original"
