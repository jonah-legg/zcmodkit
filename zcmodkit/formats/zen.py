"""Reading UE5 "Zen" cooked packages, which is how assets look inside IoStore.

A package is a header followed by export data. The header holds a summary of
section offsets, a name map, an import map and an export map. The export map
says where each export starts and how big it is.

Edit anything in the export data and those sizes have to be kept straight, so
all the parsing lives here instead of being spread around as raw offsets.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from cityhash import CityHash64

#: Where the name map starts. The summary in front of it is 60 bytes in UE 5.6.
#: It was 52 until 5.5 added two Verse cell map offsets.
NAME_MAP_OFFSET = 60

#: Size of one FExportMapEntry.
EXPORT_ENTRY_SIZE = 72

#: Where an FExportMapEntry keeps its FPackageObjectIndex fields. Outer is
#: always an export or null in practice, but class, super and template all
#: point at imported packages, so renumbering has to cover them.
EXPORT_REF_FIELDS = (24, 32, 40, 48)

#: Where the section offset table starts in the summary.
SECTION_OFFSETS_AT = 24

#: The nine section offsets, in the order the summary writes them. The two cell
#: maps came in with UE 5.5 and sit at the end, which is why the summary grew
#: from 52 bytes to 60.
SECTION_NAMES = (
    "imported_public_export_hashes",
    "import_map",
    "export_map",
    "export_bundle_entries",
    "dependency_bundle_headers",
    "dependency_bundle_entries",
    "imported_package_names",
    "cell_import_map",
    "cell_export_map",
)

#: Verse cell maps. Empty in every package this game ships. They came in with
#: UE 5.5, and physically they sit between the export map and the export bundle
#: entries even though the summary writes their offsets last.
CELL_SECTIONS = ("cell_import_map", "cell_export_map")

#: The sections in the order they are laid out, which is not the order the
#: summary lists them. A section runs to wherever the next one in this order
#: starts, so an empty section has its start and end in the same place.
LAYOUT_ORDER = (
    "imported_public_export_hashes",
    "import_map",
    "export_map",
    "cell_import_map",
    "cell_export_map",
    "export_bundle_entries",
    "dependency_bundle_headers",
    "dependency_bundle_entries",
    "imported_package_names",
)

#: Version stamp Unreal writes into the name map for its hash algorithm.
NAME_HASH_VERSION = 0xC1640000


#: The four kinds of FPackageObjectIndex, taken from the top two bits.
IMPORT_EXPORT = 0
IMPORT_SCRIPT = 1
IMPORT_PACKAGE = 2
IMPORT_NULL = 3

_INDEX_BITS = 62
_INDEX_MASK = (1 << _INDEX_BITS) - 1


def name_hash(text: str) -> int:
    """The hash a Zen name map stores next to a name.

    CityHash64 of the lowercased name. Narrow names hash their UTF-8 bytes,
    wide ones hash UTF-16. Checked against 223,196 names out of the shipped
    game and it matched every one. Every name in this game is narrow, so the
    wide branch is what the engine does rather than something confirmed here.
    """
    lowered = text.lower()
    if text.isascii():
        return CityHash64(lowered.encode("utf-8"))
    return CityHash64(lowered.encode("utf-16-le"))


def package_import(package_index: int, hash_index: int) -> int:
    """An FPackageObjectIndex pointing at an export of an imported package.

    The two indexes are positions in this package's own tables: which imported
    package, and which entry of ImportedPublicExportHashes. Confirmed against
    40,036 of them, none out of range.
    """
    return (IMPORT_PACKAGE << _INDEX_BITS) | (package_index << 32) | hash_index


def split_import(value: int) -> tuple[int, int, int]:
    """Pull an FPackageObjectIndex apart into (kind, package index, hash index).

    The two indexes only mean anything when the kind is IMPORT_PACKAGE.
    """
    kind = value >> _INDEX_BITS
    index = value & _INDEX_MASK
    return kind, index >> 32, index & 0xFFFFFFFF


@dataclass(frozen=True)
class NameMap:
    """A parsed Zen name map. Counts, hashes, a header per name, the strings."""

    names: list[str]
    hashes: list[int]
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start


def read_name_map(data: bytes | bytearray, at: int) -> NameMap:
    """Parse the name map that starts at `at`.

    Packages carry two of these. The main one right after the summary, and
    ImportedPackageNames at the back of the header.
    """
    (count,) = struct.unpack_from("<I", data, at)
    if count == 0:
        # An empty batch is just the count. Nothing follows it, so reading on
        # would walk straight into whatever section comes next.
        return NameMap([], [], at, at + 4)
    (string_bytes,) = struct.unpack_from("<I", data, at + 4)
    hashes_at = at + 16
    headers_at = hashes_at + count * 8
    strings_at = headers_at + count * 2
    if strings_at + string_bytes > len(data):
        raise PackageError(f"name map at {at} runs past the end of the package")

    names, hashes, pos = [], [], strings_at
    for i in range(count):
        first, second = data[headers_at + i * 2], data[headers_at + i * 2 + 1]
        wide = bool(first & 0x80)
        length = ((first & 0x7F) << 8) | second
        width = length * 2 if wide else length
        raw = bytes(data[pos : pos + width])
        if len(raw) != width:
            raise PackageError(f"name {i} in the map at {at} is truncated")
        names.append(
            raw.decode("utf-16-le") if wide else raw.decode("utf-8", "replace")
        )
        hashes.append(struct.unpack_from("<Q", data, hashes_at + i * 8)[0])
        pos += width
    if pos - strings_at != string_bytes:
        raise PackageError(
            f"name map at {at} consumed {pos - strings_at} bytes, "
            f"header declares {string_bytes}"
        )
    return NameMap(names, hashes, at, pos)


def write_name_map(names: list[str]) -> bytes:
    """Build a name map blob. Order is kept, the hashes get recomputed.

    Nothing sorts these, so a new name can go on the end. Checked 4,000 real
    packages and not one of them had a sorted map.
    """
    if not names:
        return struct.pack("<I", 0)
    encoded, headers = [], bytearray()
    for name in names:
        wide = not name.isascii()
        raw = name.encode("utf-16-le") if wide else name.encode("utf-8")
        length = len(raw) // 2 if wide else len(raw)
        if length > 0x7FFF:
            raise PackageError(f"name is too long for a name map: {name!r}")
        headers += bytes([(0x80 if wide else 0) | (length >> 8), length & 0xFF])
        encoded.append(raw)
    body = b"".join(encoded)
    out = bytearray(struct.pack("<II", len(names), len(body)))
    out += struct.pack("<Q", NAME_HASH_VERSION)
    out += b"".join(struct.pack("<Q", name_hash(n)) for n in names)
    return bytes(out + headers + body)


class PackageError(ValueError):
    """A cooked package would not parse, or failed one of the checks."""


@dataclass(frozen=True)
class Export:
    """One export's slice of the export data, measured from the header end."""

    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size


class ZenPackage:
    """A parsed view of cooked package bytes.

    Parsing is cheap and read only. To change something, edit the buffer and
    parse it again rather than poking at this object.
    """

    def __init__(self, data: bytes | bytearray):
        self.data = data
        if len(data) < NAME_MAP_OFFSET:
            raise PackageError(f"too short to be a package: {len(data)} bytes")
        self._read_summary()
        self._read_names()
        self._read_exports()

    # -- summary ---------------------------------------------------------

    def _read_summary(self) -> None:
        d = self.data
        (self.has_versioning,) = struct.unpack_from("<I", d, 0)
        (self.header_size,) = struct.unpack_from("<I", d, 4)
        (self.package_flags,) = struct.unpack_from("<I", d, 16)
        (self.cooked_header_size,) = struct.unpack_from("<I", d, 20)
        self.section_offsets = list(struct.unpack_from("<9i", d, SECTION_OFFSETS_AT))
        for i, name in enumerate(SECTION_NAMES):
            setattr(self, name + "_offset", self.section_offsets[i])
        self.import_map_offset = self.section_offsets[1]
        self.export_map_offset = self.section_offsets[2]
        # The export map runs up to wherever the next section starts.
        self.export_map_end = self.section_offsets[3]
        if self.has_versioning:
            raise PackageError("versioned packages are not supported")
        if not 0 < self.header_size <= len(d):
            raise PackageError(
                f"headerSize {self.header_size} outside package of {len(d)} bytes"
            )

    # -- name map --------------------------------------------------------

    def _read_names(self) -> None:
        name_map = read_name_map(self.data, NAME_MAP_OFFSET)
        if name_map.end > self.header_size:
            raise PackageError("name map runs past the end of the header")
        (self.name_hash_version,) = struct.unpack_from(
            "<Q", self.data, NAME_MAP_OFFSET + 8
        )
        self.name_map = name_map
        self.names = name_map.names
        self.name_map_end = name_map.end

    # -- export map ------------------------------------------------------

    def _read_exports(self) -> None:
        span = self.export_map_end - self.export_map_offset
        if span < 0 or span % EXPORT_ENTRY_SIZE:
            raise PackageError(
                f"export map span {span} is not a whole number of entries"
            )
        self.exports = []
        for i in range(span // EXPORT_ENTRY_SIZE):
            at = self.export_map_offset + i * EXPORT_ENTRY_SIZE
            self.exports.append(Export(*struct.unpack_from("<QQ", self.data, at)))

    def export_entry_offset(self, index: int) -> int:
        """Where an export map entry sits, for callers that need to patch it."""
        return self.export_map_offset + index * EXPORT_ENTRY_SIZE

    # -- sections --------------------------------------------------------

    def section_range(self, name: str) -> tuple[int, int]:
        """Where one header section starts and stops.

        A section runs to wherever the next one starts, going by LAYOUT_ORDER
        rather than by the order the summary lists them. Plenty of sections are
        empty, and an empty one shares its offset with the section after it, so
        picking the next largest offset instead would skip a whole section.
        """
        try:
            i = LAYOUT_ORDER.index(name)
        except ValueError:
            raise PackageError(f"no header section called {name!r}") from None
        start = self.section_offsets[SECTION_NAMES.index(name)]
        if i + 1 == len(LAYOUT_ORDER):
            return start, self.header_size
        nxt = self.section_offsets[SECTION_NAMES.index(LAYOUT_ORDER[i + 1])]
        return start, nxt

    @property
    def public_export_hashes(self) -> list[int]:
        """Export hashes of imported objects, indexed by the import map."""
        start, end = self.section_range("imported_public_export_hashes")
        return list(struct.unpack_from(f"<{(end - start) // 8}Q", self.data, start))

    @property
    def imports(self) -> list[int]:
        """The import map, as raw FPackageObjectIndex values."""
        start, end = self.section_range("import_map")
        return list(struct.unpack_from(f"<{(end - start) // 8}Q", self.data, start))

    @property
    def imported_package_names(self) -> list[str]:
        """Names of the packages this one imports, in container order.

        Runs alongside the imported package ids in the container header, so the
        two have to be kept in step. Worth knowing that the loader resolves by
        id and never reads these: 68 packages out of 2,686 sampled carry a name
        that does not hash to the id sat next to it, left over from a rename,
        and they load fine.
        """
        return read_name_map(self.data, self.section_offsets[6]).names

    @property
    def imported_package_tail(self) -> list[int]:
        """One uint32 per imported package, tucked behind ImportedPackageNames.

        The summary has no offset for this, so the only way to find it is to
        parse the name batch and take what is left before headerSize. It came
        out as exactly four bytes per imported package on all 8,000 packages
        sampled, and 97% of the values are zero.

        What the numbers mean is not something worked out here. They are kept
        as they are, and a new imported package gets a zero, which is what
        every other entry holds in the assets this is used on.
        """
        end = read_name_map(self.data, self.section_offsets[6]).end
        count = (self.header_size - end) // 4
        return list(struct.unpack_from(f"<{count}I", self.data, end))

    # -- regions ---------------------------------------------------------

    def export_data_range(self) -> tuple[int, int]:
        """Byte range of the export data, everything past the header."""
        return self.header_size, len(self.data)

    def export_at(self, relative_offset: int) -> int | None:
        """Which export covers an offset, counting from the header end."""
        for i, e in enumerate(self.exports):
            if e.offset <= relative_offset < e.end:
                return i
        return None

    def __repr__(self) -> str:
        return (
            f"<ZenPackage {len(self.data)} bytes, header={self.header_size}, "
            f"names={len(self.names)}, exports={len(self.exports)}>"
        )


def verify(data: bytes | bytearray) -> ZenPackage:
    """Parse a package and check it hangs together.

    Raises `PackageError` on the first problem it finds. Returns the parsed
    package so the caller does not have to do the work twice.
    """
    pkg = ZenPackage(data)

    if not pkg.exports:
        raise PackageError("package declares no exports")

    expected = 0
    for i, e in enumerate(pkg.exports):
        if e.offset != expected:
            raise PackageError(
                f"export {i} starts at {e.offset}, expected {expected} "
                "(exports must be contiguous from 0)"
            )
        expected += e.size

    total = pkg.header_size + expected
    if total != len(data):
        raise PackageError(
            f"headerSize {pkg.header_size} + exports {expected} = {total}, "
            f"but the package is {len(data)} bytes"
        )

    if pkg.name_hash_version != NAME_HASH_VERSION:
        raise PackageError(f"unexpected name hash version 0x{pkg.name_hash_version:x}")

    names_end = read_name_map(pkg.data, pkg.section_offsets[6]).end
    tail = pkg.header_size - names_end
    if tail != 4 * len(pkg.imported_package_names):
        raise PackageError(
            f"{tail} bytes sit behind ImportedPackageNames, expected "
            f"{4 * len(pkg.imported_package_names)}, one per imported package"
        )

    if any(pkg.section_offsets[i] != pkg.section_offsets[3] for i in (7, 8)):
        raise PackageError("package has Verse cell maps, which this cannot lay out")

    if not pkg.import_map_offset <= pkg.export_map_offset <= pkg.export_map_end:
        raise PackageError("header section offsets are out of order")
    if pkg.export_map_end > pkg.header_size:
        raise PackageError("export map runs past the end of the header")

    return pkg


def splice_section(
    data: bytes | bytearray,
    section: str,
    at: int,
    old_len: int,
    new: bytes,
) -> bytearray:
    """Swap `old_len` bytes at `at` for `new`, inside the named section.

    Header sections are found by absolute offset, so growing one moves every
    section after it. Which sections those are cannot be worked out from the
    offset alone: empty sections share their offset with the section that
    follows, so naming the section being edited is the only way to say whether
    the bytes go before or after it. Sections later in LAYOUT_ORDER shift by
    the size change, the target and everything before it stay put, and
    headerSize moves with the total.

    Export data is left alone. Export offsets are measured from the end of the
    header rather than the start of the file, so they stay correct by
    themselves.

    Pass `section="name_map"` for the name map, which sits ahead of all nine
    sections and shifts every one of them.
    """
    pkg = ZenPackage(data)
    if section == "name_map":
        first_moved, bounds = 0, (NAME_MAP_OFFSET, pkg.name_map_end)
    else:
        try:
            first_moved = LAYOUT_ORDER.index(section) + 1
        except ValueError:
            raise PackageError(f"no header section called {section!r}") from None
        bounds = pkg.section_range(section)

    end = at + old_len
    if not bounds[0] <= at <= end <= bounds[1]:
        raise PackageError(
            f"splice at {at}..{end} is outside {section} ({bounds[0]}..{bounds[1]})"
        )

    delta = len(new) - old_len
    out = bytearray(data)
    out[at:end] = new
    if delta:
        moved = {SECTION_NAMES.index(n) for n in LAYOUT_ORDER[first_moved:]}
        for i in moved:
            struct.pack_into(
                "<i", out, SECTION_OFFSETS_AT + i * 4, pkg.section_offsets[i] + delta
            )
        struct.pack_into("<I", out, 4, pkg.header_size + delta)
    return out


def append_to_section(data: bytes | bytearray, section: str, new: bytes) -> bytearray:
    """Stick bytes on the end of a header section."""
    if section == "name_map":
        at = ZenPackage(data).name_map_end
    else:
        at = ZenPackage(data).section_range(section)[1]
    return splice_section(data, section, at, 0, new)


def renumber_imported_packages(
    data: bytes | bytearray, first: int, delta: int
) -> bytearray:
    """Shift the imported-package index of every reference at or past `first`.

    Adding a package to the container's import list moves everything after it
    along, and each FPackageObjectIndex holds that position rather than a
    package id. Both the import map and the export map carry these, so both
    get walked. Miss the export map and a class or template quietly resolves to
    the wrong asset.
    """
    pkg = ZenPackage(data)
    out = bytearray(data)

    def fix(at: int) -> None:
        (value,) = struct.unpack_from("<Q", out, at)
        kind, package_index, hash_index = split_import(value)
        if kind == IMPORT_PACKAGE and package_index >= first:
            struct.pack_into(
                "<Q", out, at, package_import(package_index + delta, hash_index)
            )

    import_start, import_end = pkg.section_range("import_map")
    for at in range(import_start, import_end, 8):
        fix(at)
    for i in range(len(pkg.exports)):
        base = pkg.export_entry_offset(i)
        for field in EXPORT_REF_FIELDS:
            fix(base + field)
    return out
