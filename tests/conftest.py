"""Shared fixtures. Anything needing a real install is marked `game`."""

import struct

import pytest

import zcmodkit
from zcmodkit.formats.zen import EXPORT_ENTRY_SIZE, NAME_HASH_VERSION, NAME_MAP_OFFSET


@pytest.fixture(scope="session")
def kit():
    """An open ModKit, or skip the test if the game is not installed."""
    try:
        k = zcmodkit.open()
    except FileNotFoundError:
        pytest.skip("Star Wars: Zero Company is not installed")
    yield k
    k.close()


def _name_map(names: list[str]) -> bytes:
    """A Zen name map. Counts, hashes, a header per name, then the strings."""
    encoded = [n.encode("utf-8") for n in names]
    body = b"".join(encoded)
    out = bytearray(struct.pack("<II", len(names), len(body)))
    out += struct.pack("<Q", NAME_HASH_VERSION)
    out += b"".join(struct.pack("<Q", i) for i in range(len(names)))  # hashes
    for raw in encoded:
        out += bytes([(len(raw) >> 8) & 0x7F, len(raw) & 0xFF])  # narrow, big-endian
    return bytes(out) + body


def make_package(*export_payloads: bytes, names: tuple[str, ...] = ()) -> bytes:
    """A minimal cooked Zen package, for tests that need no game install.

    Produces something `zen.verify` accepts: contiguous exports from 0, a real
    name map, and section offsets in order.
    """
    payloads = export_payloads or (b"",)
    name_map = _name_map(list(names))
    import_map = NAME_MAP_OFFSET + len(name_map)
    export_map = import_map  # no imports
    export_map_end = export_map + EXPORT_ENTRY_SIZE * len(payloads)
    header_size = export_map_end

    header = bytearray(header_size)
    struct.pack_into("<I", header, 0, 0)  # bHasVersioningInfo
    struct.pack_into("<I", header, 4, header_size)
    struct.pack_into("<i", header, 28, import_map)
    struct.pack_into("<i", header, 32, export_map)
    struct.pack_into("<i", header, 36, export_map_end)
    header[NAME_MAP_OFFSET : NAME_MAP_OFFSET + len(name_map)] = name_map

    at = 0
    for i, payload in enumerate(payloads):
        struct.pack_into(
            "<QQ", header, export_map + i * EXPORT_ENTRY_SIZE, at, len(payload)
        )
        at += len(payload)
    return bytes(header) + b"".join(payloads)


def fstring(text: str) -> bytes:
    """Write an FString the way a cooked package stores one."""
    raw = text.encode("ascii") + b"\x00"
    return struct.pack("<i", len(raw)) + raw
