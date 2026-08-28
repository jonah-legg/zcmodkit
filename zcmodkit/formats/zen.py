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

#: Where the name map starts. The summary in front of it is 60 bytes in UE 5.6.
#: It was 52 until 5.5 added two Verse cell map offsets.
NAME_MAP_OFFSET = 60

#: Size of one FExportMapEntry.
EXPORT_ENTRY_SIZE = 72

#: Version stamp Unreal writes into the name map for its hash algorithm.
NAME_HASH_VERSION = 0xC1640000


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
        (self.import_map_offset,) = struct.unpack_from("<i", d, 28)
        (self.export_map_offset,) = struct.unpack_from("<i", d, 32)
        # Whatever field comes after the export map in this engine version,
        # its value is where the export map stops. That is all we need, and it
        # works whether or not the Verse cell offsets sit in between.
        (self.export_map_end,) = struct.unpack_from("<i", d, 36)
        if self.has_versioning:
            raise PackageError("versioned packages are not supported")
        if not 0 < self.header_size <= len(d):
            raise PackageError(
                f"headerSize {self.header_size} outside package of {len(d)} bytes"
            )

    # -- name map --------------------------------------------------------

    def _read_names(self) -> None:
        d = self.data
        count, string_bytes = struct.unpack_from("<II", d, NAME_MAP_OFFSET)
        (self.name_hash_version,) = struct.unpack_from("<Q", d, NAME_MAP_OFFSET + 8)
        hashes = NAME_MAP_OFFSET + 16
        headers = hashes + count * 8
        strings = headers + count * 2
        if strings + string_bytes > self.header_size:
            raise PackageError("name map runs past the end of the header")

        self.name_hashes_offset = hashes
        self.name_strings_offset = strings
        self.name_string_bytes = string_bytes
        self.names: list[str] = []
        self._name_spans: list[tuple[int, int]] = []

        at = strings
        for i in range(count):
            first, second = d[headers + i * 2], d[headers + i * 2 + 1]
            is_utf16 = bool(first & 0x80)
            length = ((first & 0x7F) << 8) | second
            width = length * 2 if is_utf16 else length
            raw = bytes(d[at : at + width])
            if len(raw) != width:
                raise PackageError(f"name {i} runs past the end of the package")
            self.names.append(
                raw.decode("utf-16-le") if is_utf16 else raw.decode("utf-8", "replace")
            )
            self._name_spans.append((at, width))
            at += width
        consumed = at - strings
        if consumed != string_bytes:
            raise PackageError(
                f"name map consumed {consumed} bytes, header declares {string_bytes}"
            )

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

    if not pkg.import_map_offset <= pkg.export_map_offset <= pkg.export_map_end:
        raise PackageError("header section offsets are out of order")
    if pkg.export_map_end > pkg.header_size:
        raise PackageError("export map runs past the end of the header")

    return pkg
