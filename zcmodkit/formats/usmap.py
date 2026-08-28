"""Reading .usmap mappings files.

Cooked packages store property values but not the names or types of the fields
they belong to. A mappings file fills that in, which is the only reason editing
a value by name is possible at all.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

MAGIC = 0x30C4

#: The format revisions that change how we read things.
VERSION_LONG_FNAME = 2
VERSION_LARGE_ENUMS = 3


class MappingsError(ValueError):
    """A mappings file would not parse, or does not match this asset."""


class PropertyType:
    """EPropertyType, the way a mappings file writes it."""

    BYTE = 0
    BOOL = 1
    INT = 2
    FLOAT = 3
    OBJECT = 4
    NAME = 5
    DELEGATE = 6
    DOUBLE = 7
    ARRAY = 8
    STRUCT = 9
    STR = 10
    TEXT = 11
    INTERFACE = 12
    MULTICAST_DELEGATE = 13
    WEAK_OBJECT = 14
    LAZY_OBJECT = 15
    ASSET_OBJECT = 16
    SOFT_OBJECT = 17
    UINT64 = 18
    UINT32 = 19
    UINT16 = 20
    INT64 = 21
    INT16 = 22
    INT8 = 23
    MAP = 24
    SET = 25
    ENUM = 26
    FIELD_PATH = 27
    OPTIONAL = 28

    NAMES: ClassVar[dict[int, str]] = {
        BYTE: "Byte",
        BOOL: "Bool",
        INT: "Int",
        FLOAT: "Float",
        OBJECT: "Object",
        NAME: "Name",
        DELEGATE: "Delegate",
        DOUBLE: "Double",
        ARRAY: "Array",
        STRUCT: "Struct",
        STR: "Str",
        TEXT: "Text",
        INTERFACE: "Interface",
        MULTICAST_DELEGATE: "MulticastDelegate",
        WEAK_OBJECT: "WeakObject",
        LAZY_OBJECT: "LazyObject",
        ASSET_OBJECT: "AssetObject",
        SOFT_OBJECT: "SoftObject",
        UINT64: "UInt64",
        UINT32: "UInt32",
        UINT16: "UInt16",
        INT64: "Int64",
        INT16: "Int16",
        INT8: "Int8",
        MAP: "Map",
        SET: "Set",
        ENUM: "Enum",
        FIELD_PATH: "FieldPath",
        OPTIONAL: "Optional",
    }


@dataclass
class TypeInfo:
    """A property's type, plus any inner types it wraps."""

    kind: int
    struct_name: str | None = None
    enum_name: str | None = None
    inner: list[TypeInfo] = field(default_factory=list)

    @property
    def name(self) -> str:
        return PropertyType.NAMES.get(self.kind, f"Unknown({self.kind})")

    def __repr__(self) -> str:
        extra = self.struct_name or self.enum_name or ""
        return f"{self.name}{'<' + extra + '>' if extra else ''}"


@dataclass
class PropertyInfo:
    """One property of a schema that actually gets written out."""

    name: str
    schema_index: int
    array_size: int
    type: TypeInfo

    def __repr__(self) -> str:
        return f"<Property {self.name} {self.type!r} @{self.schema_index}>"


@dataclass
class Schema:
    """A class or struct, and its properties in the order they get written."""

    name: str
    super_name: str | None
    property_count: int
    properties: list[PropertyInfo]

    def __repr__(self) -> str:
        return f"<Schema {self.name} properties={len(self.properties)}>"


class Mappings:
    """Schemas for every class and struct in one build of the game."""

    def __init__(
        self,
        names: list[str],
        enums: dict[str, dict[int, str]],
        schemas: dict[str, Schema],
        version: int,
    ):
        self.names = names
        self.enums = enums
        self.schemas = schemas
        self.version = version

    @classmethod
    def load(cls, path: str | Path) -> Mappings:
        """Parse a .usmap off disk."""
        return cls.loads(Path(path).read_bytes())

    @classmethod
    def loads(cls, data: bytes) -> Mappings:
        """Parse .usmap bytes."""
        (magic,) = struct.unpack_from("<H", data, 0)
        if magic != MAGIC:
            raise MappingsError(f"not a .usmap file (magic 0x{magic:04x})")
        version = data[2]
        # bHasVersioning is written as a 32-bit bool.
        (has_versioning,) = struct.unpack_from("<I", data, 3)
        if has_versioning:
            raise MappingsError("versioned mappings files are not supported")
        compression = data[7]
        compressed, _uncompressed = struct.unpack_from("<II", data, 8)
        body = data[16:]
        if compression != 0:
            raise MappingsError(
                f"compressed mappings are not supported (method {compression}); "
                "export an uncompressed .usmap"
            )
        if compressed != len(body):
            raise MappingsError(
                f"mappings declare {compressed} bytes but {len(body)} follow the header"
            )
        return cls._read_body(body, version)

    @staticmethod
    def _read_body(b: bytes, version: int) -> Mappings:
        at = 0

        def u8() -> int:
            nonlocal at
            at += 1
            return b[at - 1]

        def u16() -> int:
            nonlocal at
            v = struct.unpack_from("<H", b, at)[0]
            at += 2
            return v

        def u32() -> int:
            nonlocal at
            v = struct.unpack_from("<I", b, at)[0]
            at += 4
            return v

        count = u32()
        names: list[str] = []
        for _ in range(count):
            length = u16() if version >= VERSION_LONG_FNAME else u8()
            names.append(b[at : at + length].decode("utf-8", "replace"))
            at += length

        def u64() -> int:
            nonlocal at
            v = struct.unpack_from("<Q", b, at)[0]
            at += 8
            return v

        # Every entry has its numeric value first, then its name.
        enums: dict[str, dict[int, str]] = {}
        for _ in range(u32()):
            enum_name = names[u32()]
            entries = u16() if version >= VERSION_LARGE_ENUMS else u8()
            enums[enum_name] = {u64(): names[u32()] for _ in range(entries)}

        def read_type() -> TypeInfo:
            kind = u8()
            info = TypeInfo(kind)
            if kind == PropertyType.ENUM:
                info.inner.append(read_type())
                info.enum_name = names[u32()]
            elif kind == PropertyType.STRUCT:
                info.struct_name = names[u32()]
            elif kind in (PropertyType.ARRAY, PropertyType.SET, PropertyType.OPTIONAL):
                info.inner.append(read_type())
            elif kind == PropertyType.MAP:
                info.inner.append(read_type())
                info.inner.append(read_type())
            return info

        schemas: dict[str, Schema] = {}
        for _ in range(u32()):
            schema_name = names[u32()]
            super_index = u32()
            super_name = None if super_index == 0xFFFFFFFF else names[super_index]
            prop_count = u16()
            serializable = u16()
            props: list[PropertyInfo] = []
            for _ in range(serializable):
                schema_index = u16()
                array_size = u8()
                prop_name = names[u32()]
                props.append(
                    PropertyInfo(prop_name, schema_index, array_size, read_type())
                )
            schemas[schema_name] = Schema(schema_name, super_name, prop_count, props)

        # Later revisions tack on sections we do not need, module paths and
        # so on. Stopping after the schemas is fine. Running off the end is not.
        if at > len(b):
            raise MappingsError("mappings body is truncated")
        return Mappings(names, enums, schemas, version)

    def schema(self, name: str) -> Schema:
        """Look up a schema by class or struct name."""
        try:
            return self.schemas[name]
        except KeyError:
            raise MappingsError(f"no schema for {name!r} in these mappings") from None

    def properties(self, name: str) -> list[PropertyInfo]:
        """A schema's properties, inherited ones included, base class first."""
        chain, current = [], name
        seen = set()
        while current and current not in seen:
            seen.add(current)
            schema = self.schemas.get(current)
            if schema is None:
                break
            chain.append(schema)
            current = schema.super_name
        out: list[PropertyInfo] = []
        for schema in reversed(chain):
            out.extend(schema.properties)
        return out

    def __repr__(self) -> str:
        return (
            f"<Mappings version={self.version} names={len(self.names)} "
            f"enums={len(self.enums)} schemas={len(self.schemas)}>"
        )


#: Which build of the game these bundled mappings came from.
BUNDLED_BUILD = "SWZeroCompany-5.6.1-196320+++ProjectBruno+Stable-a1e7f571"

_bundled: Mappings | None = None


def bundled() -> Mappings:
    """The mappings that ship with zcmodkit, parsed once and kept around.

    They describe one build of the game. If a patch moves a struct around, the
    parse stops landing exactly where it should and the editor raises instead
    of writing a value to the wrong place.
    """
    global _bundled
    if _bundled is None:
        path = Path(__file__).parent.parent / "data" / "mappings.usmap"
        if not path.is_file():
            raise MappingsError(
                f"bundled mappings are missing from the install ({path}). "
                "Editing values needs them; text edits do not."
            )
        _bundled = Mappings.load(path)
    return _bundled
