"""Package facade: assignments on a package reach the submodule that owns the state.

A package that was split into submodules keeps its old module-level names. Tests and
deployment hooks assign to those names on the package (`monkeypatch.setattr(pkg, "WORK", p)`);
the code that reads them lives in a submodule. `install_facade` makes both views agree.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterable, Mapping


class _FacadeModule(types.ModuleType):
    """Package type with write-through and read-through for submodule-owned names."""

    _facade_owned: Mapping[str, types.ModuleType]
    _facade_mirrors: tuple[types.ModuleType, ...]

    def _targets(self, name: str) -> list[types.ModuleType]:
        targets = []
        owner = self._facade_owned.get(name)
        if owner is not None:
            targets.append(owner)
        targets.extend(sub for sub in self._facade_mirrors if name in vars(sub) and sub is not owner)
        return targets

    def __getattribute__(self, name: str) -> object:
        # Owned names are read from the owner, so the package never returns a stale copy.
        owned = types.ModuleType.__getattribute__(self, "__dict__").get("_facade_owned")
        if owned is not None and name in owned:
            return getattr(owned[name], name)
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value: object) -> None:
        if name.startswith("_facade_"):
            super().__setattr__(name, value)
            return
        for sub in self._targets(name):
            setattr(sub, name, value)
        # The package also keeps an entry for every name it exposes. Tools that inspect
        # `vars(package)` (pytest's monkeypatch reads the old value from `__dict__` to
        # undo a patch) then see the name and restore it instead of deleting it.
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        found = False
        for sub in self._targets(name):
            if name in vars(sub):
                delattr(sub, name)
                found = True
        if name in self.__dict__:
            super().__delattr__(name)
        elif not found:
            raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __dir__(self) -> list[str]:
        return sorted({*super().__dir__(), *self._facade_owned})


def install_facade(
    package: str,
    mirrors: Iterable[types.ModuleType] = (),
    owned: Mapping[str, types.ModuleType] | None = None,
) -> None:
    """Make the package `package` (a `__name__`) forward assignments to its submodules.

    `owned` maps a name to the single submodule that owns it: a write on the package goes
    to that submodule, and a read of a name the package does not hold itself is answered
    by that submodule, so the package never keeps a stale copy.
    `mirrors` are submodules that merely import or define a global of the same name: a write
    on the package is also applied to every mirror that has that name, and to the package
    itself, so each module sees the assigned value.
    """
    pkg = sys.modules[package]
    pkg.__class__ = _FacadeModule
    pkg._facade_owned = dict(owned or {})
    pkg._facade_mirrors = tuple(mirrors)
    for name, owner in pkg._facade_owned.items():
        if hasattr(owner, name):
            pkg.__dict__[name] = getattr(owner, name)
