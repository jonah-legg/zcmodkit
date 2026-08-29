"""Editing cooked assets."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..formats.iostore import package_id
from ..formats.zen import (
    EXPORT_ENTRY_SIZE,
    IMPORT_PACKAGE,
    ZenPackage,
    append_to_section,
    package_import,
    read_name_map,
    renumber_imported_packages,
    splice_section,
    split_import,
    write_name_map,
)


class AssetEditor:
    """Edits strings inside one cooked asset.

    A cooked package records how long each of its exports is. Change the length
    of a string and those numbers go stale, so this fixes them up afterwards.
    That is why the replacement text can be any length.
    """

    def __init__(
        self, package_path: str, data: bytes, imported_packages: list[int] | None = None
    ):
        self.package_path = package_path
        self.data = bytearray(data)
        self.changes = 0
        # The ids of the packages this one imports live in the container header
        # rather than the package, so they get carried alongside. add_import
        # adds to this list and the builder ships whatever is here.
        self.imported_packages = list(imported_packages or [])
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

    # -- growing the header ----------------------------------------------

    def add_name(self, name: str) -> int:
        """Put a new name in the package name map and give back its index.

        Names go on the end. Nothing sorts them, so nothing else has to move,
        and the hash gets worked out from the name itself. If the name is
        already there this just returns where it is.
        """
        if name in self.names:
            return self.names.index(name)
        old = read_name_map(self.data, self.package.name_map.start)
        rebuilt = write_name_map([*old.names, name])
        self.data = splice_section(self.data, "name_map", old.start, old.size, rebuilt)
        self._reparse()
        self.changes += 1
        return len(self.names) - 1

    def add_imported_package(self, package_path: str) -> int:
        """Add a package to the list of ones this asset imports.

        The container keeps these ids in ascending order and the loader binary
        searches them, so a new one lands in the middle rather than on the end.
        Everything after it moves along by one, and every reference holding one
        of those positions has to be renumbered to match.
        """
        pid = package_id(package_path)
        if pid in self.imported_packages:
            return self.imported_packages.index(pid)

        at = sum(1 for existing in self.imported_packages if existing < pid)
        self.data = renumber_imported_packages(self.data, at, 1)

        # Two things run alongside the ids and both need an entry at the same
        # spot: the names, and the uint32 array behind them. The summary has no
        # offset for that array, so the whole section gets rebuilt together
        # rather than spliced in two places.
        names = self.package.imported_package_names
        tail = self.package.imported_package_tail
        start, end = self.package.section_range("imported_package_names")
        rebuilt = write_name_map([*names[:at], package_path, *names[at:]])
        rebuilt += struct.pack(f"<{len(tail) + 1}I", *tail[:at], 0, *tail[at:])
        self.data = splice_section(
            self.data, "imported_package_names", start, end - start, rebuilt
        )

        self.imported_packages.insert(at, pid)
        self._reparse()
        self.changes += 1
        return at

    def add_import(self, package_path: str, export_hash: int) -> int:
        """Import one object out of another package. Gives back its import index.

        `export_hash` is the public export hash of the object being pointed at,
        which is how the loader finds it once the package is mounted. Three
        things get added: the package to the import list, the hash to
        ImportedPublicExportHashes, and an entry to the import map that ties
        the two together.
        """
        package_index = self.add_imported_package(package_path)

        hashes = self.package.public_export_hashes
        if export_hash in hashes:
            hash_index = hashes.index(export_hash)
        else:
            hash_index = len(hashes)
            self.data = append_to_section(
                self.data,
                "imported_public_export_hashes",
                struct.pack("<Q", export_hash),
            )
            self._reparse()

        entry = package_import(package_index, hash_index)
        existing = self.package.imports
        if entry in existing:
            return existing.index(entry)

        self.data = append_to_section(self.data, "import_map", struct.pack("<Q", entry))
        self._reparse()
        self.changes += 1
        return len(existing)

    # -- editing export data ----------------------------------------------

    def splice_export_data(self, at: int, old_len: int, new: bytes) -> AssetEditor:
        """Swap `old_len` bytes at `at` for `new`, inside the export data.

        The export holding those bytes grows or shrinks to match and every
        export after it slides along. `at` is an absolute offset into the
        package and has to land inside an export, not on the seam between two,
        because otherwise there is no saying which of them the new bytes join.
        """
        start, end = self.package.export_data_range()
        if not start <= at <= at + old_len <= end:
            raise ValueError(
                f"splice at {at}..{at + old_len} is outside the export data "
                f"({start}..{end})"
            )
        relative = at - self.package.header_size
        if self.package.export_at(relative) is None:
            raise ValueError(f"offset {at} is not inside any export")

        delta = len(new) - old_len
        self.data[at : at + old_len] = new
        if delta:
            self._shift_exports(relative, delta)
        else:
            self._reparse()
        self.changes += 1
        return self

    def import_ref(self, import_index: int) -> int:
        """How the export data refers to an import.

        Object references in cooked data are one signed int: positive counts
        exports from one, negative counts imports from one, zero is null.
        """
        return -(import_index + 1)

    def resolve_ref(self, ref: int) -> str | None:
        """What an object reference points at, for checking an edit landed."""
        if ref == 0:
            return None
        if ref > 0:
            index = ref - 1
            return f"export[{index}]" if index < len(self.package.exports) else None
        index = -ref - 1
        if index >= len(self.package.imports):
            return None
        kind, package, _hash = split_import(self.package.imports[index])
        if kind != IMPORT_PACKAGE:
            return f"import[{index}]"
        names = self.package.imported_package_names
        return names[package] if package < len(names) else None

    def find_object_map(
        self, *, entries: int | None = None, referencing: str | None = None
    ) -> ObjectMap:
        """Find a Map<Object, Object> in the export data by what it holds.

        A cooked map is a zero (nothing to remove), a count, then that many
        key and value pairs, each one an object reference. Rather than walking
        every property in front of it, this scans for that shape and keeps only
        the ones where every reference resolves to something real, which throws
        out almost everything by itself.

        Narrow it with `entries` for the number of pairs and `referencing` for
        a substring one of the packages has to contain. Raises unless exactly
        one map matches, so a change never lands on a lucky second candidate.
        """
        found = [
            m
            for m in self.object_maps()
            if (entries is None or len(m.entries) == entries)
            and (referencing is None or any(referencing in p for p in m.packages))
        ]
        if len(found) != 1:
            what = f"entries={entries} referencing={referencing!r}"
            raise LookupError(
                f"wanted exactly one object map in {self.package_path} ({what}), "
                f"found {len(found)}"
            )
        return found[0]

    def object_maps(
        self, min_entries: int = 1, max_entries: int = 256
    ) -> list[ObjectMap]:
        """Every run of bytes in the export data shaped like an object map."""
        start, end = self.package.export_data_range()
        out = []
        for at in range(start, end - 8):
            removals, count = struct.unpack_from("<ii", self.data, at)
            if removals != 0 or not min_entries <= count <= max_entries:
                continue
            if at + 8 + count * 8 > end:
                continue
            pairs, packages, ok = [], [], True
            for i in range(count):
                key, value = struct.unpack_from("<ii", self.data, at + 8 + i * 8)
                names = []
                for ref in (key, value):
                    # A null reference is a real thing to store, so it counts
                    # as resolved. Anything else that will not resolve means
                    # this run of bytes is not a map.
                    if ref == 0:
                        names.append("")
                        continue
                    resolved = self.resolve_ref(ref)
                    if resolved is None:
                        ok = False
                        break
                    names.append(resolved)
                if not ok:
                    break
                pairs.append((key, value))
                packages.extend(names)
            if ok:
                out.append(ObjectMap(self, at, pairs, packages))
        return out

    def add_gameplay_tag(
        self, beside: str, tag: str, expect: int | None = None
    ) -> AssetEditor:
        """Add a tag to the container that already holds `beside`.

        Containers are not labelled in cooked data, so the way to point at one
        is to name a tag already in it. The new tag goes on the end of that
        container, the count goes up by one, and the name map gains an entry if
        it does not have the tag already.
        """
        # The name map sits in front of the export data, so growing it first
        # keeps the offsets found below valid.
        index = self.add_name(tag)

        names = self.names
        if beside not in names:
            raise KeyError(f"{beside!r} is not in the name map of {self.package_path}")
        anchor = names.index(beside)

        start, end = self.package.export_data_range()
        needle = struct.pack("<II", anchor, 0)
        hits, at = [], start
        while (i := self.data.find(needle, at, end)) >= 0:
            hits.append(i)
            at = i + 1
        if expect is not None and len(hits) != expect:
            raise ValueError(
                f"expected {expect} container(s) holding {beside!r} in "
                f"{self.package_path}, found {len(hits)}"
            )
        if not hits:
            raise KeyError(f"{beside!r} is in the name map but never referenced")

        for pos in reversed(hits):
            count_at, count = self._tag_container_count(pos, start)
            struct.pack_into("<i", self.data, count_at, count + 1)
            after = count_at + 4 + count * 8
            self.splice_export_data(after, 0, struct.pack("<II", index, 0))
        return self

    def remove_gameplay_tag(self, tag: str, expect: int | None = None) -> AssetEditor:
        """Take a tag out of the tag container it sits in.

        A container is a count followed by that many FNames. retarget_name can
        point an entry somewhere else but the count stays put, so the container
        keeps its length. Some of this game's checks care about that, so this
        drops the entry and brings the count down with it.

        Finding the count means stepping back one entry at a time from the tag
        until a number turns up that describes the entries after it, with every
        one of them a real name. Pass `expect` if you know how many containers
        should be touched.
        """
        names = self.names
        if tag not in names:
            raise KeyError(f"{tag!r} is not in the name map of {self.package_path}")
        index = names.index(tag)

        start, end = self.package.export_data_range()
        needle = struct.pack("<II", index, 0)
        hits, at = [], start
        while (i := self.data.find(needle, at, end)) >= 0:
            hits.append(i)
            at = i + 1
        if expect is not None and len(hits) != expect:
            raise ValueError(
                f"expected {expect} container(s) holding {tag!r} in "
                f"{self.package_path}, found {len(hits)}"
            )
        if not hits:
            raise KeyError(f"{tag!r} is in the name map but never referenced")

        # Work backwards so the offsets found above stay put.
        for pos in reversed(hits):
            count_at, count = self._tag_container_count(pos, start)
            struct.pack_into("<i", self.data, count_at, count - 1)
            self.splice_export_data(pos, 8, b"")
        return self

    def _tag_container_count(self, entry_at: int, start: int) -> tuple[int, int]:
        """Where the count of the container holding this entry sits, and its value.

        The entry could be anywhere in the container, so try each position in
        turn. A candidate only counts if the number is right for how many
        entries follow it and every one of them reads as a name this package
        actually has.
        """
        for slot in range(64):
            count_at = entry_at - 8 * slot - 4
            if count_at < start:
                break
            (count,) = struct.unpack_from("<i", self.data, count_at)
            if not slot < count <= 64:
                continue
            if count_at + 4 + count * 8 > len(self.data):
                continue
            if all(
                struct.unpack_from("<II", self.data, count_at + 4 + i * 8)[0]
                < len(self.names)
                and struct.unpack_from("<II", self.data, count_at + 4 + i * 8)[1] == 0
                for i in range(count)
            ):
                return count_at, count
        raise ValueError(
            f"could not find the container holding the tag at {entry_at} in "
            f"{self.package_path}"
        )

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


@dataclass
class ObjectMap:
    """A Map<Object, Object> sat in an asset's export data.

    `entries` holds the raw object references, `packages` the names they
    resolve to, so an edit can be checked against what is actually there.
    """

    editor: AssetEditor
    offset: int
    entries: list[tuple[int, int]]
    packages: list[str]

    def append(self, key_import: int, value_import: int | None) -> ObjectMap:
        """Add a pair, given the import indexes to point the two halves at.

        Pass None for the value to store a null reference, which is what the
        game does for a primary specialisation that has no secondary.
        """
        key = self.editor.import_ref(key_import)
        value = 0 if value_import is None else self.editor.import_ref(value_import)
        end = self.offset + 8 + len(self.entries) * 8
        # Bump the count first. It lives in front of the pairs, so inserting
        # afterwards leaves it where it is.
        struct.pack_into("<i", self.editor.data, self.offset + 4, len(self.entries) + 1)
        self.editor.splice_export_data(end, 0, struct.pack("<ii", key, value))
        self.entries.append((key, value))
        return self

    @property
    def named_entries(self) -> list[tuple[str, str]]:
        """The pairs as package names, which is what you want when checking."""
        return list(zip(self.packages[0::2], self.packages[1::2], strict=True))

    def __repr__(self) -> str:
        return f"<ObjectMap @{self.offset} entries={len(self.entries)}>"
