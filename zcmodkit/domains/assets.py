"""Editing cooked assets."""

from __future__ import annotations

import struct

from ..formats.zen import EXPORT_ENTRY_SIZE, ZenPackage


class AssetEditor:
    """Edits strings inside one cooked asset.

    A cooked package records how long each of its exports is. Change the length
    of a string and those numbers go stale, so this fixes them up afterwards.
    That is why the replacement text can be any length.
    """

    def __init__(self, package_path: str, data: bytes):
        self.package_path = package_path
        self.data = bytearray(data)
        self.changes = 0
        self._reparse()

    def _reparse(self) -> None:
        self.package = ZenPackage(self.data)

    @property
    def names(self) -> list[str]:
        """The package name map: class names, object paths, gameplay tags."""
        return self.package.names

    @staticmethod
    def _fstrings(text: str) -> list[bytes]:
        """Both ways a cooked package might have stored `text`.

        Unreal uses the narrow encoding where it can, but an asset authored
        with wide strings keeps them, so check for both.
        """
        forms = []
        if text.isascii():
            raw = text.encode("ascii") + b"\x00"
            forms.append(struct.pack("<i", len(raw)) + raw)
        wide = text.encode("utf-16-le") + b"\x00\x00"
        forms.append(struct.pack("<i", -(len(wide) // 2)) + wide)
        return forms

    def _find(self, text: str) -> tuple[bytes, list[int]]:
        """The stored form of `text`, and where it turns up in the export data.

        Only the export data gets searched. Anything matching in the header
        belongs to the name map or one of the other indexes, and splicing bytes
        in there would wreck the package.
        """
        start, end = self.package.export_data_range()
        for form in self._fstrings(text):
            hits, at = [], start
            while (i := self.data.find(form, at, end)) >= 0:
                hits.append(i)
                at = i + 1
            if hits:
                return form, hits
        return b"", []

    def find_text(self, text: str) -> list[int]:
        """Where every string equal to `text` sits in the export data."""
        return self._find(text)[1]

    def replace_text(self, old: str, new: str) -> AssetEditor:
        """Replace every string equal to `old`. Any length is allowed."""
        old_raw, hits = self._find(old)
        if not hits:
            in_names = any(old == n for n in self.names)
            hint = (
                " It is in the package name map, which replace_text cannot "
                "resize; try retarget_name()."
                if in_names
                else ""
            )
            raise KeyError(f"{old!r} is not a string in {self.package_path}.{hint}")

        # Keep whatever encoding the asset already used.
        wide = struct.unpack_from("<i", old_raw)[0] < 0
        new_raw = self._fstrings(new)[-1 if wide else 0]
        delta = len(new_raw) - len(old_raw)

        # Work backwards so the offsets we already found stay put.
        for pos in reversed(hits):
            self.data[pos : pos + len(old_raw)] = new_raw
            self.changes += 1
            if delta:
                self._shift_exports(pos - self.package.header_size, delta)
        self._reparse()
        return self

    def retarget_name(
        self, old: str, new: str, expect: int | None = None
    ) -> AssetEditor:
        """Point references to the name `old` at the name `new` instead.

        Gameplay tags, class names and object paths are not text in the export
        data. They sit in the package name map, and the export data points at
        them by index. Changing which index a reference uses means the name map
        never moves, nothing gets resized, and no hash needs recomputing.

        Both names have to be in the package name map already. Pass `expect` if
        you know how many references there should be.
        """
        names = self.names
        if old not in names:
            raise KeyError(
                f"{old!r} is not in the name map of {self.package_path}. "
                f"It has {len(names)} names."
            )
        if new not in names:
            raise KeyError(
                f"{new!r} is not in the name map of {self.package_path}, and "
                "names cannot be added yet. Pick one the package already uses."
            )
        old_index, new_index = names.index(old), names.index(new)

        # An FName is a name-map index plus an instance number. Match both so
        # we do not hit some unrelated pair of integers that looks the same.
        start, end = self.package.export_data_range()
        needle = struct.pack("<II", old_index, 0)
        replacement = struct.pack("<II", new_index, 0)
        hits, at = [], start
        while (i := self.data.find(needle, at, end)) >= 0:
            hits.append(i)
            at = i + 1

        if expect is not None and len(hits) != expect:
            raise ValueError(
                f"expected {expect} reference(s) to {old!r} in "
                f"{self.package_path}, found {len(hits)}"
            )
        if not hits:
            raise KeyError(f"{old!r} is in the name map but never referenced")

        for pos in hits:
            self.data[pos : pos + 8] = replacement
            self.changes += 1
        return self

    def _shift_exports(self, rel_pos: int, delta: int) -> None:
        """Resize the export holding rel_pos, and move the ones after it."""
        for i, export in enumerate(self.package.exports):
            at = self.package.export_map_offset + i * EXPORT_ENTRY_SIZE
            if export.offset <= rel_pos < export.end:
                struct.pack_into("<Q", self.data, at + 8, export.size + delta)
            elif export.offset > rel_pos:
                struct.pack_into("<Q", self.data, at, export.offset + delta)
        self._reparse()

    def __repr__(self) -> str:
        return f"<AssetEditor {self.package_path!r} changes={self.changes}>"
