"""ZeroCompany ModKit. Build Star Wars: Zero Company mods from Python."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from . import game
from .domains import AssetEditor
from .formats import (
    IoStoreReader,
    IoStoreWriter,
    LocRes,
    PakReader,
    PakWriter,
    package_id,
)
from .formats.iostore import CHUNK_EXPORT_BUNDLE_DATA
from .formats.zen import ZenPackage
from .mod import DEFAULT_PRIORITY, Mod

__version__ = "0.1.0"
__all__ = [
    "AssetEditor",
    "InstalledMod",
    "IoStoreReader",
    "IoStoreWriter",
    "LocRes",
    "Mod",
    "ModKit",
    "PakReader",
    "PakWriter",
    "open",
]

_CONTAINERS = ("pakchunk0-Windows.utoc", "pakchunk1-Windows.utoc")
_BASE_PAK = "pakchunk0-Windows.pak"
_LOCRES = "SWZeroCompany/Content/Localization/Game/en/Game.locres"


@dataclass
class InstalledMod:
    """A mod container sat in the game's ~mods folder."""

    path: Path
    package_ids: list[int]
    assets: list[str]

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def priority(self) -> int:
        """The number the filename starts with. Lower wins. 999 if there is none."""
        head = self.stem.split("_", 1)[0]
        return int(head) if head.isdigit() else 999

    @property
    def name(self) -> str:
        """The mod name, with the priority prefix and _P suffix stripped off."""
        head, sep, rest = self.stem.partition("_")
        body = rest if sep and head.isdigit() else self.stem
        return body.removesuffix("_P")

    def __repr__(self) -> str:
        n = len(self.assets)
        return f"<InstalledMod {self.priority:03d} {self.name!r} assets={n}>"


class ModKit:
    """A read only view of the installed game, and where mods start."""

    def __init__(self, root: Path):
        self.root = root
        self.paks = game.paks_dir(root)
        self._readers: list[IoStoreReader] | None = None

    @property
    def containers(self) -> list[IoStoreReader]:
        """The game's IoStore containers, opened the first time they are used."""
        if self._readers is None:
            self._readers = [
                IoStoreReader(self.paks / n)
                for n in _CONTAINERS
                if (self.paks / n).is_file()
            ]
        return self._readers

    def read_package(self, package_path: str) -> bytes:
        """Read a cooked package out of the game by its /Game/... path."""
        pid = package_id(package_path)
        for r in self.containers:
            chunk = r.by_package.get(pid)
            if chunk is not None:
                return r.read_chunk(chunk)
        raise KeyError(f"{package_path} is not in any container")

    def read_companions(self, package_path: str) -> list[tuple[bytes, bytes]]:
        """Every chunk a package owns bar its exports, as (chunk id, payload).

        About a quarter of packages keep bulk data this way, and a mod has to
        ship it next to the package it edits.
        """
        pid = package_id(package_path)
        for r in self.containers:
            if pid not in r.by_package:
                continue
            return [
                (c.id, r.read_chunk(c))
                for c in r.chunks_for(pid)
                if c.type != CHUNK_EXPORT_BUNDLE_DATA
            ]
        raise KeyError(f"{package_path} is not in any container")

    def imported_packages(self, package_path: str) -> list[int]:
        """The package ids a package depends on, from the game's own header.

        A mod has to pass these along or the package it ships will not load.
        """
        pid = package_id(package_path)
        for r in self.containers:
            if pid in r.by_package:
                return r.imported_packages(pid)
        raise KeyError(f"{package_path} is not in any container")

    def public_exports(self, package_path: str) -> dict[str, int]:
        """The objects in a package that other packages are allowed to import.

        Keyed by object name, valued by the hash the importer has to quote.
        Exports with no hash are private to the package and left out.
        """
        data = self.read_package(package_path)
        pkg = ZenPackage(data)
        out = {}
        for i in range(len(pkg.exports)):
            at = pkg.export_entry_offset(i)
            (name_index,) = struct.unpack_from("<I", data, at + 16)
            (export_hash,) = struct.unpack_from("<Q", data, at + 56)
            if export_hash and name_index < len(pkg.names):
                out[pkg.names[name_index]] = export_hash
        return out

    def public_export_hash(
        self, package_path: str, object_name: str | None = None
    ) -> int:
        """The hash needed to import one object out of a package.

        Defaults to the object named after the package itself, which is the
        main asset and nearly always the one worth importing.
        """
        exports = self.public_exports(package_path)
        wanted = object_name or package_path.rsplit("/", 1)[-1]
        try:
            return exports[wanted]
        except KeyError:
            raise KeyError(
                f"{package_path} has no public export called {wanted!r}. "
                f"It offers: {', '.join(sorted(exports)) or 'none'}"
            ) from None

    def has_package(self, package_path: str) -> bool:
        """Whether the game has this package at all."""
        pid = package_id(package_path)
        return any(pid in r.by_package for r in self.containers)

    @cached_property
    def text(self) -> LocRes:
        """The game's text table. Handy for finding a string and its key."""
        with PakReader(self.paks / _BASE_PAK) as pak:
            return LocRes.loads(pak.read(_LOCRES))

    def paks_file(self, path: str) -> bytes:
        """Read a plain file out of the game's main pak.

        Not everything the engine reads is a package. AssetRegistry.bin is the
        one that matters for modding: it is where the customizer gets its list
        of parts and their AllowedSlots, so it is the only place a part's gate
        can actually be changed.
        """
        with PakReader(self.paks / _BASE_PAK) as pak:
            return pak.read(path)

    def create_mod(self, name: str, priority: int = DEFAULT_PRIORITY) -> Mod:
        """Start a new mod. `priority` settles who wins if two mods clash."""
        return Mod(self, name, priority)

    def installed_mods(self) -> list[InstalledMod]:
        """Installed mods, best priority first, which is the order they win in."""
        out = []
        for utoc in (self.paks / "~mods").glob("*.utoc"):
            with IoStoreReader(utoc) as r:
                out.append(InstalledMod(utoc, sorted(r.by_package), list(r.files)))
        return sorted(out, key=lambda m: (m.priority, m.name))

    def conflicts(self) -> dict[str, list[InstalledMod]]:
        """Assets that more than one installed mod edits, keyed by file name.

        Only the best-priority copy of an asset gets loaded, so anything in
        here means one mod is quietly overriding another.
        """
        owners: dict[str, list[InstalledMod]] = {}
        for mod in self.installed_mods():
            for name in mod.assets:
                owners.setdefault(name, []).append(mod)
        return {k: v for k, v in owners.items() if len(v) > 1}

    def close(self) -> None:
        for r in self._readers or []:
            r.close()
        self._readers = None

    def __repr__(self) -> str:
        return f"<ModKit {self.root}>"


def open(path: str | os.PathLike | None = None) -> ModKit:  # noqa: A001
    """Open the game install. Finds Steam and Epic on its own if you let it."""
    return ModKit(game.find_install(path))
