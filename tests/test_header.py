"""Growing a package header: names, imports, and the section offsets."""

import struct

import pytest
from conftest import make_package

from zcmodkit.domains import AssetEditor
from zcmodkit.formats.zen import (
    IMPORT_PACKAGE,
    LAYOUT_ORDER,
    PackageError,
    ZenPackage,
    append_to_section,
    name_hash,
    package_import,
    read_name_map,
    renumber_imported_packages,
    splice_section,
    split_import,
    verify,
    write_name_map,
)


def test_name_hash_is_cityhash_of_the_lowercased_name():
    from cityhash import CityHash64

    assert name_hash("AllowedSlots") == CityHash64(b"allowedslots")
    assert name_hash("ALLOWEDSLOTS") == name_hash("allowedslots")


def test_write_name_map_round_trips():
    names = ["Alpha", "br.Some.Tag", "/Script/Engine"]
    blob = write_name_map(names)
    parsed = read_name_map(blob, 0)
    assert parsed.names == names
    assert parsed.hashes == [name_hash(n) for n in names]
    assert parsed.end == len(blob)


def test_an_empty_name_map_is_just_a_count():
    assert write_name_map([]) == struct.pack("<I", 0)
    assert read_name_map(write_name_map([]), 0).names == []


def test_package_import_round_trips():
    value = package_import(11, 36)
    assert split_import(value) == (IMPORT_PACKAGE, 11, 36)


def test_splicing_nothing_leaves_the_package_alone():
    data = make_package(b"payload", names=("Alpha",))
    for section in LAYOUT_ORDER:
        start, end = ZenPackage(data).section_range(section)
        for at in (start, end):
            assert bytes(splice_section(data, section, at, 0, b"")) == data


def test_growing_a_section_moves_the_ones_after_it():
    data = make_package(b"payload", names=("Alpha",))
    before = ZenPackage(data)
    grown = ZenPackage(
        append_to_section(data, "imported_public_export_hashes", struct.pack("<Q", 7))
    )
    assert grown.public_export_hashes == [7]
    assert grown.header_size == before.header_size + 8
    # The hashes section starts where it did; everything after it shifted.
    assert grown.section_offsets[0] == before.section_offsets[0]
    assert grown.section_offsets[1:] == [o + 8 for o in before.section_offsets[1:]]


def test_growing_the_header_leaves_the_export_data_where_it_was():
    data = make_package(b"first", b"second", names=("Alpha",))
    before = ZenPackage(data)
    grown = ZenPackage(append_to_section(data, "import_map", struct.pack("<Q", 0)))
    assert grown.data[grown.header_size :] == data[before.header_size :]
    assert [(e.offset, e.size) for e in grown.exports] == [
        (e.offset, e.size) for e in before.exports
    ]
    assert verify(grown.data)


def test_a_grown_section_can_be_shrunk_back():
    data = make_package(b"payload", names=("Alpha",))
    grown = append_to_section(data, "import_map", struct.pack("<Q", 0))
    end = ZenPackage(grown).section_range("import_map")[1]
    assert bytes(splice_section(grown, "import_map", end - 8, 8, b"")) == data


def test_splicing_outside_a_section_is_refused():
    data = make_package(b"payload", names=("Alpha",))
    start, _ = ZenPackage(data).section_range("import_map")
    with pytest.raises(PackageError, match="outside"):
        splice_section(data, "import_map", start - 8, 0, b"\x00" * 8)


def test_splicing_an_unknown_section_is_refused():
    data = make_package(b"payload")
    with pytest.raises(PackageError, match="no header section"):
        splice_section(data, "not_a_section", 100, 0, b"")


def test_renumbering_only_touches_package_imports():
    data = bytearray(make_package(b"payload", names=("Alpha",)))
    pkg = ZenPackage(bytes(data))
    # A script import in the class slot must survive untouched.
    script = (1 << 62) | 999
    struct.pack_into("<Q", data, pkg.export_entry_offset(0) + 32, script)
    struct.pack_into("<Q", data, pkg.export_entry_offset(0) + 48, package_import(3, 1))
    out = renumber_imported_packages(bytes(data), 2, 1)
    base = pkg.export_entry_offset(0)
    assert struct.unpack_from("<Q", out, base + 32)[0] == script
    assert split_import(struct.unpack_from("<Q", out, base + 48)[0]) == (
        IMPORT_PACKAGE,
        4,
        1,
    )


def test_renumbering_leaves_earlier_indexes_alone():
    data = bytearray(make_package(b"payload"))
    pkg = ZenPackage(bytes(data))
    struct.pack_into("<Q", data, pkg.export_entry_offset(0) + 40, package_import(1, 0))
    out = renumber_imported_packages(bytes(data), 5, 1)
    assert split_import(
        struct.unpack_from("<Q", out, pkg.export_entry_offset(0) + 40)[0]
    ) == (IMPORT_PACKAGE, 1, 0)


def test_add_name_appends_and_keeps_the_rest_intact():
    editor = AssetEditor("x", make_package(b"payload", names=("Alpha", "Beta")))
    index = editor.add_name("br.New.Tag")
    assert index == 2
    assert editor.names == ["Alpha", "Beta", "br.New.Tag"]
    assert verify(editor.data)
    assert editor.data[editor.package.header_size :] == b"payload"


def test_add_name_is_a_no_op_when_the_name_is_already_there():
    editor = AssetEditor("x", make_package(b"payload", names=("Alpha",)))
    assert editor.add_name("Alpha") == 0
    assert editor.changes == 0
