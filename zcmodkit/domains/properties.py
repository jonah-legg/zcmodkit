"""Finding and editing properties inside cooked export data.

Cooked exports use Unreal's unversioned property serialization. A small header
says which of a schema's properties are there, then the values follow one after
another with nothing to name them.

So reading one value means walking every property in front of it. That is what
this does, using schemas out of a mappings file.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..formats.usmap import Mappings, PropertyType

#: Types that are always the same size, and how many bytes they take.
FIXED_WIDTH = {
    PropertyType.INT8: 1,
    PropertyType.BYTE: 1,
    PropertyType.BOOL: 1,
    PropertyType.INT16: 2,
    PropertyType.UINT16: 2,
    PropertyType.INT: 4,
    PropertyType.UINT32: 4,
    PropertyType.FLOAT: 4,
    PropertyType.INT64: 8,
    PropertyType.UINT64: 8,
    PropertyType.DOUBLE: 8,
    PropertyType.NAME: 8,  # FName: mapped index + number
    PropertyType.OBJECT: 4,  # package object index
    PropertyType.WEAK_OBJECT: 4,  # serialized the same way as a hard reference
    PropertyType.LAZY_OBJECT: 16,  # FUniqueObjectGuid
}

#: struct format for each numeric type.
NUMERIC_FORMAT = {
    PropertyType.INT8: "<b",
    PropertyType.BYTE: "<B",
    PropertyType.INT16: "<h",
    PropertyType.UINT16: "<H",
    PropertyType.INT: "<i",
    PropertyType.UINT32: "<I",
    PropertyType.FLOAT: "<f",
    PropertyType.INT64: "<q",
    PropertyType.UINT64: "<Q",
    PropertyType.DOUBLE: "<d",
}


class PropertyError(ValueError):
    """A property could not be found, or its type is not handled yet."""


@dataclass
class Fragment:
    """One run of the header. Skip a few properties, then read some values."""

    skip: int
    has_zeroes: bool
    values: int
    is_last: bool

    @classmethod
    def unpack(cls, packed: int) -> Fragment:
        return cls(
            skip=packed & 0x007F,
            has_zeroes=bool(packed & 0x0080),
            is_last=bool(packed & 0x0100),
            values=packed >> 9,
        )


@dataclass
class Located:
    """Where a property's value sits, and what it reads as right now."""

    name: str
    offset: int
    size: int
    type_kind: int
    value: object

    def __repr__(self) -> str:
        return f"<{self.name} @{self.offset} +{self.size} = {self.value!r}>"


def read_header(data: bytes, at: int) -> tuple[list[int], list[bool], int]:
    """Parse an unversioned header.

    Gives back the schema indices that are present, whether each one was zeroed
    out and therefore not written, and where the values start.
    """
    present: list[int] = []
    zeroed: list[bool] = []
    zero_flags: list[bool] = []
    index = 0
    while True:
        (packed,) = struct.unpack_from("<H", data, at)
        at += 2
        frag = Fragment.unpack(packed)
        index += frag.skip
        for _ in range(frag.values):
            present.append(index)
            zero_flags.append(frag.has_zeroes)
            index += 1
        if frag.is_last:
            break

    # Properties in zero-marked fragments each get a bit saying whether the
    # value was left out because it was zero.
    zero_count = sum(1 for flag in zero_flags if flag)
    if zero_count:
        mask_bytes = (zero_count + 7) // 8
        mask = int.from_bytes(data[at : at + mask_bytes], "little")
        at += mask_bytes
        bit = 0
        for flag in zero_flags:
            if flag:
                zeroed.append(bool(mask >> bit & 1))
                bit += 1
            else:
                zeroed.append(False)
    else:
        zeroed = [False] * len(present)
    return present, zeroed, at


#: Structs Unreal writes with its own code instead of as properties.
#: Sizes are what they take up in cooked data.
def write_header(present: list[int]) -> bytes:
    """Build an unversioned header listing exactly these schema indices.

    Runs of consecutive indices share a fragment, which is what the cooker
    does. No zero mask is written, so every property named here has to have a
    value after it.
    """
    out = bytearray()
    index = 0
    i = 0
    while i < len(present):
        skip = present[i] - index
        run = 1
        while i + run < len(present) and present[i + run] == present[i] + run:
            run += 1
        if not 0 <= skip <= 127 or not 1 <= run <= 127:
            raise PropertyError(
                f"cannot encode a fragment skipping {skip} with {run} values"
            )
        index = present[i] + run
        is_last = i + run >= len(present)
        out += struct.pack("<H", skip | (0x100 if is_last else 0) | (run << 9))
        i += run
    return bytes(out)


#: Structs Unreal writes with its own code instead of as properties.
NATIVE_STRUCTS = {
    "GameplayTag": 8,  # a single FName
    "Guid": 16,
    "Color": 4,
    "LinearColor": 16,
    "IntPoint": 8,
    "Vector2D": 16,
    "Vector": 24,
    "Vector4": 32,
    "Rotator": 24,
    "Quat": 32,
}


def _fname(data: bytes, at: int) -> tuple[int, int]:
    """An FName in cooked data. A name-map index and a number."""
    return struct.unpack_from("<II", data, at)


def _fstring_size(data: bytes, at: int) -> int:
    """An FString: a length, then that many characters. Negative means UTF-16."""
    (length,) = struct.unpack_from("<i", data, at)
    return 4 + (abs(length) * 2 if length < 0 else length)


#: ETextHistoryType values. An FText is a flags word, a history type, and then
#: whatever that history keeps. Only the three the game's cooked data uses are
#: here; the rest raise rather than guess, because a wrong size walks the rest
#: of the export off into nothing.
TEXT_HISTORY_NONE = 0xFF
TEXT_HISTORY_BASE = 0
TEXT_HISTORY_STRING_TABLE_ENTRY = 11


def _text_size(data: bytes, at: int) -> int:
    """How many bytes the FText at `at` takes up."""
    cursor = at + 4  # flags
    (history,) = struct.unpack_from("<B", data, cursor)
    cursor += 1
    if history == TEXT_HISTORY_NONE:
        (has_string,) = struct.unpack_from("<I", data, cursor)
        cursor += 4
        if has_string:
            cursor += _fstring_size(data, cursor)
    elif history == TEXT_HISTORY_BASE:
        for _ in range(3):  # namespace, key, source string
            cursor += _fstring_size(data, cursor)
    elif history == TEXT_HISTORY_STRING_TABLE_ENTRY:
        cursor += 8  # the table's FName
        cursor += _fstring_size(data, cursor)  # the key within it
    else:
        raise PropertyError(
            f"text history type {history} at {at} is not one this reads yet"
        )
    return cursor - at


def value_size(data: bytes, at: int, info, mappings: Mappings) -> int:
    """How many bytes the value at `at` takes up."""
    kind = info.kind
    if kind in FIXED_WIDTH:
        return FIXED_WIDTH[kind]
    if kind == PropertyType.STRUCT:
        name = info.struct_name
        # If a struct has a schema it is written as unversioned properties,
        # even when it looks like one Unreal handles itself. FGameplayTag has
        # its own header, for example. Only fall back to the native sizes when
        # the mappings have nothing for it.
        if name in mappings.schemas:
            return skip_struct(data, at, name, mappings) - at
        if name in NATIVE_STRUCTS:
            return NATIVE_STRUCTS[name]
        raise PropertyError(f"struct {name!r} has no schema and is not a known native")
    if kind == PropertyType.STR:
        return _fstring_size(data, at)
    if kind == PropertyType.TEXT:
        return _text_size(data, at)
    if kind in (PropertyType.SOFT_OBJECT, PropertyType.ASSET_OBJECT):
        return 12  # FName plus a sub-path FString index
    if kind == PropertyType.INTERFACE:
        return 4  # just the object reference
    if kind == PropertyType.DELEGATE:
        return 12  # FScriptDelegate: object reference plus a function name
    if kind == PropertyType.MULTICAST_DELEGATE:
        # An invocation list of FScriptDelegate. Cooked defaults are normally
        # empty, since bindings happen at runtime.
        (count,) = struct.unpack_from("<i", data, at)
        return 4 + count * 12
    if kind == PropertyType.ARRAY:
        (count,) = struct.unpack_from("<i", data, at)
        cursor = at + 4
        for _ in range(count):
            cursor += value_size(data, cursor, info.inner[0], mappings)
        return cursor - at
    if kind in (PropertyType.MAP, PropertyType.SET):
        # Both start with a count of keys to remove, which is always zero in
        # cooked data because there is no base object to remove them from.
        (removals,) = struct.unpack_from("<i", data, at)
        if removals:
            raise PropertyError(
                f"{info!r} wants to remove {removals} keys, which cooked data "
                "should never do"
            )
        (count,) = struct.unpack_from("<i", data, at + 4)
        cursor = at + 8
        for _ in range(count):
            for inner in info.inner:
                cursor += value_size(data, cursor, inner, mappings)
        return cursor - at
    raise PropertyError(f"unsupported property type {info!r}")


def skip_struct(data: bytes, at: int, struct_name: str, mappings: Mappings) -> int:
    """Where a struct written as unversioned properties finishes."""
    present, zeroed, cursor = read_header(data, at)
    props = mappings.properties(struct_name)
    by_index = {p.schema_index: p for p in props}
    for schema_index, is_zero in zip(present, zeroed, strict=True):
        if is_zero:
            continue
        info = by_index.get(schema_index)
        if info is None:
            raise PropertyError(
                f"{struct_name} has no property at schema index {schema_index}; "
                "the mappings do not match this asset"
            )
        cursor += value_size(data, cursor, info.type, mappings)
    return cursor


def read_struct(
    data: bytes, at: int, struct_name: str, mappings: Mappings
) -> tuple[dict[str, Located], int]:
    """Every property in a struct, and where the struct finishes."""
    present, zeroed, cursor = read_header(data, at)
    by_index = {p.schema_index: p for p in mappings.properties(struct_name)}
    out: dict[str, Located] = {}
    for schema_index, is_zero in zip(present, zeroed, strict=True):
        info = by_index.get(schema_index)
        if info is None:
            raise PropertyError(
                f"{struct_name} has no property at schema index {schema_index}; "
                "the mappings do not match this asset"
            )
        if is_zero:
            out[info.name] = Located(info.name, -1, 0, info.type.kind, 0)
            continue
        size = value_size(data, cursor, info.type, mappings)
        out[info.name] = Located(
            info.name,
            cursor,
            size,
            info.type.kind,
            _decode(data, cursor, info.type.kind),
        )
        cursor += size
    return out, cursor


def _decode(data: bytes, at: int, kind: int):
    """The Python value for a fixed-width property, or None if it is not one."""
    fmt = NUMERIC_FORMAT.get(kind)
    if fmt:
        return struct.unpack_from(fmt, data, at)[0]
    if kind == PropertyType.NAME:
        return _fname(data, at)
    return None


def write_number(data: bytearray, located: Located, value: float) -> None:
    """Overwrite a fixed-width number where it sits.

    Numbers never change width, so nothing else in the package has to move.
    """
    fmt = NUMERIC_FORMAT.get(located.type_kind)
    if fmt is None:
        raise PropertyError(f"{located.name} is not a numeric property")
    if located.offset < 0:
        raise PropertyError(
            f"{located.name} was omitted from this asset because it is zero, "
            "so there is nothing to overwrite"
        )
    struct.pack_into(fmt, data, located.offset, value)
