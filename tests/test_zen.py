"""The Zen package parser and the checks it runs."""

import struct

import pytest
from conftest import fstring, make_package

from zcmodkit.formats.zen import (
    EXPORT_ENTRY_SIZE,
    NAME_MAP_OFFSET,
    PackageError,
    ZenPackage,
    verify,
)


def test_parses_a_minimal_package():
    pkg = ZenPackage(make_package(b"payload"))
    assert len(pkg.exports) == 1
    assert pkg.exports[0].offset == 0
    assert pkg.exports[0].size == len(b"payload")


def test_reads_the_name_map():
    pkg = ZenPackage(make_package(b"", names=("Alpha", "br.Some.Tag")))
    assert pkg.names == ["Alpha", "br.Some.Tag"]


def test_multiple_exports_are_contiguous():
    pkg = ZenPackage(make_package(b"a" * 10, b"b" * 20, b"c" * 5))
    assert [(e.offset, e.size) for e in pkg.exports] == [(0, 10), (10, 20), (30, 5)]
    assert pkg.export_at(15) == 1
    assert pkg.export_at(999) is None


def test_export_data_range_starts_after_the_header():
    data = make_package(b"payload")
    pkg = ZenPackage(data)
    start, end = pkg.export_data_range()
    assert data[start:end] == b"payload"


def test_verify_accepts_a_well_formed_package():
    assert verify(make_package(fstring("HELLO"), names=("N",)))


def test_verify_rejects_a_truncated_package():
    with pytest.raises(PackageError, match="too short"):
        ZenPackage(b"\x00" * 8)


def test_verify_rejects_a_size_mismatch():
    data = bytearray(make_package(b"payload"))
    pkg = ZenPackage(bytes(data))
    # Say the export is longer than the bytes that are actually there.
    struct.pack_into("<Q", data, pkg.export_map_offset + 8, 9999)
    with pytest.raises(PackageError, match="but the package is"):
        verify(bytes(data))


def test_verify_rejects_non_contiguous_exports():
    data = bytearray(make_package(b"a" * 10, b"b" * 10))
    pkg = ZenPackage(bytes(data))
    struct.pack_into("<Q", data, pkg.export_map_offset + EXPORT_ENTRY_SIZE, 4)
    with pytest.raises(PackageError, match="contiguous"):
        verify(bytes(data))


def test_verify_rejects_a_broken_name_map():
    data = bytearray(make_package(b"", names=("Alpha",)))
    # Say there are more string bytes than the names actually take up.
    struct.pack_into("<I", data, NAME_MAP_OFFSET + 4, 999)
    with pytest.raises(PackageError):
        verify(bytes(data))


def test_verify_rejects_an_unexpected_name_hash_version():
    data = bytearray(make_package(b"payload"))
    struct.pack_into("<Q", data, NAME_MAP_OFFSET + 8, 0xDEAD)
    with pytest.raises(PackageError, match="name hash version"):
        verify(bytes(data))
