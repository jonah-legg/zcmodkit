"""AssetEditor. Swapping strings, and the export bookkeeping behind it."""

import struct

import pytest
from conftest import fstring, make_package

from zcmodkit.domains import AssetEditor


def export_size(data: bytes) -> int:
    export_map, _ = struct.unpack_from("<2i", data, 32)
    return struct.unpack_from("<QQ", data, export_map)[1]


def header_size(data: bytes) -> int:
    return struct.unpack_from("<I", data, 4)[0]


def editor(*strings: str) -> AssetEditor:
    body = b"".join(fstring(s) for s in strings)
    return AssetEditor("/Game/Test", make_package(body))


@pytest.mark.parametrize("new", ["SHORT", "SAMELENGTH!", "MUCH MUCH LONGER TEXT"])
def test_replacement_keeps_bookkeeping_consistent(new):
    a = editor("PADDING", "SAMELENGTH!", "TRAILING")
    a.replace_text("SAMELENGTH!", new)
    assert header_size(a.data) + export_size(a.data) == len(a.data)
    assert a.find_text(new)
    assert not a.find_text("SAMELENGTH!") or new == "SAMELENGTH!"


def test_neighbouring_strings_survive_a_resize():
    a = editor("BEFORE", "TARGET", "AFTER")
    a.replace_text("TARGET", "A MUCH LONGER REPLACEMENT")
    assert a.find_text("BEFORE") and a.find_text("AFTER")


def test_size_delta_matches_text_delta():
    a = editor("TARGET")
    before = len(a.data)
    a.replace_text("TARGET", "TARGET++")
    assert len(a.data) - before == 2


def test_every_occurrence_is_replaced():
    a = editor("DUP", "OTHER", "DUP")
    a.replace_text("DUP", "REPLACED")
    assert a.changes == 2
    assert not a.find_text("DUP")
    assert header_size(a.data) + export_size(a.data) == len(a.data)


def test_matches_whole_strings_not_substrings():
    a = editor("CONTINUE")
    with pytest.raises(KeyError):
        a.replace_text("CONTIN", "X")  # a substring is not an FString


def test_missing_text_raises():
    with pytest.raises(KeyError):
        editor("PRESENT").replace_text("ABSENT", "X")
