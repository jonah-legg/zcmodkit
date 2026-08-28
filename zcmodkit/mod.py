"""The Mod object. Collect up edits, then build or install."""

from __future__ import annotations

import shutil
from pathlib import Path

from .domains import AssetEditor, DataTable
from .formats import IoStoreWriter, package_id
from .formats.zen import PackageError
from .formats.zen import verify as zen_verify

#: What a mod gets if it does not ask for a priority. Sits in the middle so
#: other mods can be pushed either side of it.
DEFAULT_PRIORITY = 100


class Mod:
    """One mod. Edit some assets, then build or install it."""

    def __init__(self, kit, name: str, priority: int = DEFAULT_PRIORITY):
        """`priority` runs 0 to 999. Lower wins when two mods touch one asset."""
        self.kit = kit
        self.name = name
        self.priority = priority
        self._assets: dict[str, AssetEditor] = {}
        self._tables: dict[str, DataTable] = {}

    @property
    def basename(self) -> str:
        """The name all three files share, with the priority in front.

        The engine mounts containers in reverse filename order, so the lowest
        number goes on last and wins. Checked in game with 000_ and 999_ both
        editing the same asset, and 000_ was the one that took.
        """
        return f"{self.priority:03d}_{self.name}_P"

    @property
    def changes(self) -> int:
        return sum(a.changes for a in self._assets.values()) + sum(
            t.changes for t in self._tables.values()
        )

    def asset(self, package_path: str) -> AssetEditor:
        """Open a cooked asset for editing, by its /Game/... package path."""
        if package_path not in self._assets:
            self._assets[package_path] = AssetEditor(
                package_path, self.kit.read_package(package_path)
            )
        return self._assets[package_path]

    def table(self, package_path: str) -> DataTable:
        """Open a cooked DataTable for editing, by its /Game/... package path."""
        if package_path not in self._tables:
            self._tables[package_path] = DataTable(
                package_path, bytearray(self.kit.read_package(package_path))
            )
        return self._tables[package_path]

    def build(
        self, out_dir: str | Path = "./build", verify: bool = False
    ) -> list[Path]:
        """Write the mod's three files into `out_dir`.

        Pass `verify=True` to parse every edited package again and check it
        first. A broken one raises instead of getting shipped.
        """
        edits: dict[str, bytes] = {p: bytes(a.data) for p, a in self._assets.items()}
        edits.update({p: bytes(t.data) for p, t in self._tables.items()})
        if not edits:
            raise ValueError("Mod has no changes; nothing to build.")
        writer = IoStoreWriter(container_id=package_id(f"/zcmodkit/{self.name}"))
        for path, data in edits.items():
            if verify:
                try:
                    zen_verify(data)
                except PackageError as exc:
                    raise PackageError(f"{path}: {exc}") from exc
            writer.add_package(path, data, companions=self.kit.read_companions(path))
        return list(writer.write(Path(out_dir) / self.basename))

    def install(self) -> list[Path]:
        """Build the mod and drop it into the game's ~mods folder."""
        built = self.build(Path.home() / ".zcmodkit" / "build")
        dest_dir = self.kit.paks / "~mods"
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = []
        for f in built:
            dest = dest_dir / f.name
            shutil.copy2(f, dest)
            out.append(dest)
        return out

    def uninstall(self) -> int:
        """Take this mod back out of the game. Says how many files went."""
        n = 0
        for ext in (".pak", ".utoc", ".ucas"):
            f = self.kit.paks / "~mods" / (self.basename + ext)
            if f.is_file():
                f.unlink()
                n += 1
        return n

    def __repr__(self) -> str:
        n = len(self._assets) + len(self._tables)
        return f"<Mod {self.name!r} assets={n} changes={self.changes}>"
