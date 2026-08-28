"""The mappings parser and the property walker."""

import struct

import pytest

from zcmodkit.domains.properties import Fragment, read_header
from zcmodkit.formats.usmap import (
    BUNDLED_BUILD,
    Mappings,
    MappingsError,
    PropertyType,
    bundled,
)


def test_bundled_mappings_parse():
    m = bundled()
    assert m.version >= 2
    assert len(m.schemas) > 1000
    assert len(m.names) > 1000


def test_bundled_mappings_are_cached():
    assert bundled() is bundled()


def test_bundled_build_is_recorded():
    assert "SWZeroCompany" in BUNDLED_BUILD


def test_rejects_a_file_that_is_not_a_usmap():
    with pytest.raises(MappingsError, match=r"not a .usmap"):
        Mappings.loads(b"\x00" * 64)


def test_known_schema_shape():
    """The struct behind ability costs. A community mod edits this one too."""
    m = bundled()
    props = {p.name: p for p in m.properties("AbilityCostTableRow")}
    assert props["ActionPointCost"].type.kind == PropertyType.FLOAT
    assert props["CostCategoryName"].type.kind == PropertyType.NAME
    assert props["CostCategoryTag"].type.struct_name == "GameplayTag"


def test_properties_include_inherited_ones():
    m = bundled()
    schema = m.schema("AbilityCostTableRow")
    assert schema.super_name == "TableRowBase"
    assert len(m.properties("AbilityCostTableRow")) >= len(schema.properties)


def test_unknown_schema_raises():
    with pytest.raises(MappingsError, match="no schema"):
        bundled().schema("NotARealStructName")


@pytest.mark.parametrize(
    ("packed", "skip", "values", "zeroes", "last"),
    [(0x1B80, 0, 13, True, True), (0x0300, 0, 1, False, True)],
)
def test_fragment_unpacking(packed, skip, values, zeroes, last):
    """Bit layout lifted straight off real assets."""
    f = Fragment.unpack(packed)
    assert (f.skip, f.values, f.has_zeroes, f.is_last) == (skip, values, zeroes, last)


def test_header_marks_zeroed_properties():
    # One fragment, 4 values, all flagged as maybe zero. Mask marks 1 and 3.
    frag = struct.pack("<H", (4 << 9) | 0x0100 | 0x0080)
    mask = struct.pack("<B", 0b1010)
    present, zeroed, at = read_header(frag + mask, 0)
    assert present == [0, 1, 2, 3]
    assert zeroed == [False, True, False, True]
    assert at == 3


def test_header_without_zeroes_reads_no_mask():
    frag = struct.pack("<H", (2 << 9) | 0x0100)
    present, zeroed, at = read_header(frag, 0)
    assert present == [0, 1]
    assert zeroed == [False, False]
    assert at == 2
