"""Reader and writer for UE5 IoStore containers (.utoc and .ucas).

Zero Company ships every package in IoStore and will only mount mods that are
IoStore containers too, so this is the format mods have to be written in.
"""

from __future__ import annotations

import io
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3
from cityhash import CityHash64

from . import oodle
from .pak import PakWriter

TOC_MAGIC = b"-==--==--==--==-"
HEADER_SIZE = 144
DEFAULT_BLOCK_SIZE = 64 * 1024
MOUNT_POINT = "../../../"

# EIoChunkType5
CHUNK_EXPORT_BUNDLE_DATA = 1
CHUNK_CONTAINER_HEADER = 6


def package_id(package_path: str) -> int:
    """FPackageId. CityHash64 of the lowercased package name as UTF-16."""
    return CityHash64(package_path.lower().encode("utf-16-le"))


def chunk_id(
    pkg_id: int, index: int = 0, chunk_type: int = CHUNK_EXPORT_BUNDLE_DATA
) -> bytes:
    """FIoChunkId. An 8-byte package id, a 2-byte index, a pad byte, a type."""
    return struct.pack("<QHBB", pkg_id, index, 0, chunk_type)


def chunk_hash(data: bytes) -> bytes:
    """FIoChunkHash. BLAKE3-160, padded out to 24 bytes with zeroes."""
    return blake3(data).digest(length=32)[:20] + bytes(4)


@dataclass
class Chunk:
    """One chunk inside a container."""

    id: bytes
    offset: int
    length: int
    name: str | None = None

    @property
    def package_id(self) -> int:
        return struct.unpack_from("<Q", self.id, 0)[0]

    @property
    def index(self) -> int:
        """Tells apart several chunks of the same type on one package."""
        return struct.unpack_from("<H", self.id, 8)[0]

    @property
    def type(self) -> int:
        return self.id[11]


@dataclass
class TocHeader:
    version: int = 8
    entry_count: int = 0
    block_count: int = 0
    block_entry_size: int = 12
    method_count: int = 0
    method_name_len: int = 32
    block_size: int = DEFAULT_BLOCK_SIZE
    dir_index_size: int = 0
    partition_count: int = 1
    container_id: int = 0
    container_flags: int = 8
    perfect_hash_seed_count: int = 0
    partition_size: int = 0xFFFFFFFFFFFFFFFF
    without_perfect_hash_count: int = 0


def _rstr(b: io.BytesIO) -> str:
    (n,) = struct.unpack("<i", b.read(4))
    if n == 0:
        return ""
    if n < 0:
        return b.read(-n * 2).decode("utf-16-le").rstrip(chr(0))
    return b.read(n).decode("latin-1").rstrip(chr(0))


def _wstr(s: str) -> bytes:
    raw = s.encode("latin-1") + bytes([0])
    return struct.pack("<i", len(raw)) + raw


class IoStoreReader:
    """Reads chunks out of a .utoc and .ucas pair."""

    def __init__(self, utoc: str | Path):
        self.utoc_path = Path(utoc)
        self.ucas_path = self.utoc_path.with_suffix(".ucas")
        raw = self.utoc_path.read_bytes()
        if raw[:16] != TOC_MAGIC:
            raise ValueError(f"{self.utoc_path.name}: not a .utoc")
        self._parse(raw)
        self._ucas = open(self.ucas_path, "rb")  # noqa: SIM115, closed by close()

    def close(self) -> None:
        self._ucas.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _parse(self, raw: bytes) -> None:
        h = TocHeader()
        h.version = raw[16]
        (
            hdr_size,
            h.entry_count,
            h.block_count,
            h.block_entry_size,
            h.method_count,
            h.method_name_len,
            h.block_size,
            h.dir_index_size,
            h.partition_count,
        ) = struct.unpack_from("<9I", raw, 20)
        (h.container_id,) = struct.unpack_from("<Q", raw, 56)
        h.container_flags = raw[80]
        (h.perfect_hash_seed_count,) = struct.unpack_from("<I", raw, 84)
        (h.partition_size,) = struct.unpack_from("<Q", raw, 88)
        (h.without_perfect_hash_count,) = struct.unpack_from("<I", raw, 96)
        self.header = h

        p = hdr_size
        ids = [raw[p + i * 12 : p + (i + 1) * 12] for i in range(h.entry_count)]
        p += h.entry_count * 12
        self.chunks: list[Chunk] = []
        for i in range(h.entry_count):
            ol = raw[p + i * 10 : p + (i + 1) * 10]
            self.chunks.append(
                Chunk(
                    ids[i],
                    int.from_bytes(ol[0:5], "big"),
                    int.from_bytes(ol[5:10], "big"),
                )
            )
        p += h.entry_count * 10
        p += h.perfect_hash_seed_count * 4
        p += h.without_perfect_hash_count * 4

        self.blocks: list[tuple[int, int, int, int]] = []
        for i in range(h.block_count):
            b = raw[p + i * 12 : p + (i + 1) * 12]
            self.blocks.append(
                (
                    int.from_bytes(b[0:5], "little"),
                    int.from_bytes(b[5:8], "little"),
                    int.from_bytes(b[8:11], "little"),
                    b[11],
                )
            )
        p += h.block_count * 12

        self.methods = ["None"]
        for _ in range(h.method_count):
            name = raw[p : p + h.method_name_len].split(bytes([0]))[0].decode("latin-1")
            self.methods.append(name)
            p += h.method_name_len

        self.mount_point = MOUNT_POINT
        self.files: dict[str, int] = {}
        if h.dir_index_size:
            self._parse_dir_index(raw[p : p + h.dir_index_size])
        p += h.dir_index_size
        self._meta_offset = p

        self.by_package: dict[int, Chunk] = {}
        self._all_by_package: dict[int, list[Chunk]] = {}
        self._store: dict[int, list[int]] | None = None
        for c in self.chunks:
            if c.type == CHUNK_CONTAINER_HEADER:
                continue
            self._all_by_package.setdefault(c.package_id, []).append(c)
            if c.type == CHUNK_EXPORT_BUNDLE_DATA:
                self.by_package.setdefault(c.package_id, c)

    def imported_packages(self, pkg_id: int) -> list[int]:
        """The package ids this package depends on, from the container header.

        The Zen loader uses this to pull dependencies in first. Ship a package
        claiming no imports when it has some and it quietly fails to load, so a
        mod has to carry the real list through.
        """
        if self._store is None:
            self._store = self._read_store_entries()
        return list(self._store.get(pkg_id, ()))

    def _read_store_entries(self) -> dict[int, list[int]]:
        header = next(
            (c for c in self.chunks if c.type == CHUNK_CONTAINER_HEADER), None
        )
        if header is None:
            return {}
        d = self.read_chunk(header)
        (count,) = struct.unpack_from("<I", d, 16)
        ids = struct.unpack_from(f"<{count}Q", d, 20)
        entries_at = 20 + count * 8 + 4
        out: dict[int, list[int]] = {}
        for i, pid in enumerate(ids):
            at = entries_at + i * 16
            num, offset = struct.unpack_from("<ii", d, at)
            if num:
                out[pid] = list(struct.unpack_from(f"<{num}Q", d, at + offset))
        return out

    def chunks_for(self, pkg_id: int) -> list[Chunk]:
        """Every chunk a package owns, not just its export data.

        About a quarter of this game's packages come with a bulk data chunk
        alongside. Ship the package without it and the asset is broken.
        """
        return list(self._all_by_package.get(pkg_id, ()))

    def _parse_dir_index(self, blob: bytes) -> None:
        b = io.BytesIO(blob)
        self.mount_point = _rstr(b)
        (ndirs,) = struct.unpack("<i", b.read(4))
        dirs = [struct.unpack("<4I", b.read(16)) for _ in range(ndirs)]
        (nfiles,) = struct.unpack("<i", b.read(4))
        files = [struct.unpack("<3I", b.read(12)) for _ in range(nfiles)]
        (nstr,) = struct.unpack("<i", b.read(4))
        strings = [_rstr(b) for _ in range(nstr)]

        INVALID = 0xFFFFFFFF

        def walk(dir_idx: int, prefix: str) -> None:
            while dir_idx != INVALID:
                name, first_child, next_sib, first_file = dirs[dir_idx]
                path = prefix if name == INVALID else prefix + strings[name] + "/"
                fi = first_file
                while fi != INVALID:
                    fname, next_file, user = files[fi]
                    self.files[path + strings[fname]] = user
                    fi = next_file
                if first_child != INVALID:
                    walk(first_child, path)
                dir_idx = next_sib

        if dirs:
            walk(0, "")

    def read_chunk(self, chunk: Chunk) -> bytes:
        """Read one chunk, decompressing it if it needs it."""
        bs = self.header.block_size
        first = chunk.offset // bs
        last = (chunk.offset + chunk.length - 1) // bs
        out = bytearray()
        for i in range(first, last + 1):
            off, csize, usize, method = self.blocks[i]
            self._ucas.seek(off)
            raw = self._ucas.read(csize)
            out += raw if method == 0 else oodle.decompress(raw, usize)
        start = chunk.offset - first * bs
        return bytes(out[start : start + chunk.length])

    def read_package(self, package_path: str) -> bytes:
        """Read a cooked package by its /Game/... path."""
        c = self.by_package.get(package_id(package_path))
        if c is None:
            raise KeyError(package_path)
        return self.read_chunk(c)


# The rest of FIoContainerHeader after the store entries. Optional segment
# arrays, then an offset into the trailing bytes, then constants. The offset is
# always 36 past the end of the store section, checked against every container
# the game ships and against a working community mod.
_TAIL_OFFSET_FROM_STORE_END = 36


def _header_tail(store_end: int) -> bytes:
    """The bytes that follow the store entries in a container header."""
    out = bytearray(20)  # empty optional-segment arrays
    out += struct.pack("<i", store_end + _TAIL_OFFSET_FROM_STORE_END)
    out += struct.pack("<i", 0)
    out += struct.pack("<i", 4)
    out += bytes(16)
    return bytes(out)


def container_header(
    container_id: int, packages: Sequence[tuple[int, Sequence[int]]]
) -> bytes:
    """Build the type 6 container header chunk.

    `packages` is (package id, imported package ids) for each package. The
    imports matter: the loader reads them to pull dependencies in first, and a
    package that claims none when it has some will not load.
    """
    # The loader looks packages up by binary search, so the ids have to be in
    # ascending order and the store entries have to line up with them. Every
    # container the game ships is sorted this way.
    packages = sorted(packages, key=lambda item: item[0])

    out = bytearray(b"nCoI")
    out += struct.pack("<I", 5)  # version
    out += struct.pack("<Q", container_id)
    out += struct.pack("<I", len(packages))
    for pid, _ in packages:
        out += struct.pack("<Q", pid)

    # Each FFilePackageStoreEntry is two array views of (count, offset), and the
    # offset is measured from the view itself. The arrays they point at follow
    # the entries.
    entries = bytearray()
    data = bytearray()
    entries_size = len(packages) * 16
    for i, (_, imports) in enumerate(packages):
        view_at = i * 16
        if imports:
            offset = entries_size + len(data) - view_at
            entries += struct.pack("<ii", len(imports), offset)
            for imported in imports:
                data += struct.pack("<Q", imported)
        else:
            entries += struct.pack("<ii", 0, 0)
        entries += struct.pack("<ii", 0, 0)  # no shader map hashes

    store = bytes(entries) + bytes(data)
    out += struct.pack("<I", len(store)) + store
    out += _header_tail(len(out))
    return bytes(out)


def _stub_pak() -> bytes:
    """An empty .pak. The engine needs one next to the container to spot the mod."""
    import tempfile

    import repak

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "stub.pak"
        w = repak.PakBuilder().writer(
            str(out), version=repak.Version.V11, mount_point=MOUNT_POINT
        )
        w.write_index()
        return out.read_bytes()


class IoStoreWriter:
    """Builds a .utoc and .ucas pair, plus the stub .pak that gets it noticed."""

    def __init__(
        self,
        container_id: int | None = None,
        mount_point: str = MOUNT_POINT,
        block_size: int = DEFAULT_BLOCK_SIZE,
    ):
        self.container_id = container_id if container_id is not None else 0
        self.mount_point = mount_point
        self.block_size = block_size
        #: (chunk id, payload, directory-index name or None)
        self._entries: list[tuple[bytes, bytes, str | None]] = []
        self._packages: list[tuple[int, Sequence[int]]] = []

    def add_package(
        self,
        package_path: str,
        data: bytes,
        filename: str | None = None,
        companions: Sequence[tuple[bytes, bytes]] = (),
        imports: Sequence[int] = (),
    ) -> None:
        """Add a cooked package under its /Game/... path.

        `companions` is any other chunk the package owns, usually bulk data,
        as (chunk id, payload) pairs. Ship them. Leave them out and the game
        gets a package whose bulk data has gone missing.

        `imports` is the package ids this one depends on, copied from the game's
        own container header. Leave them out and the package will not load.
        """
        pid = package_id(package_path)
        name = filename or package_path.rsplit("/", 1)[-1] + ".uasset"
        self._packages.append((pid, tuple(imports)))
        self._entries.append((chunk_id(pid), data, name))
        for cid, payload in companions:
            self._entries.append((cid, payload, None))

    def _directory_index(self, files: list[tuple[str, int]]) -> bytes:
        """Index of (file name, chunk index). Only named entries go in."""
        INVALID = 0xFFFFFFFF
        out = bytearray(_wstr(self.mount_point))
        out += struct.pack("<i", 1)
        out += struct.pack("<4I", INVALID, INVALID, INVALID, 0)  # root directory
        out += struct.pack("<i", len(files))
        for i, (_, chunk_index) in enumerate(files):
            nxt = i + 1 if i + 1 < len(files) else INVALID
            out += struct.pack("<3I", i, nxt, chunk_index)  # name, next, chunk
        out += struct.pack("<i", len(files))
        for name, _ in files:
            out += _wstr(name)
        return bytes(out)

    def write(
        self, base: str | Path, pak_files: dict[str, bytes] | None = None
    ) -> tuple[Path, Path, Path]:
        """Write out .utoc, .ucas and .pak, and give back the three paths.

        `pak_files` puts real files in the .pak that normally goes out empty.
        Assets belong in the container, not here, but a few things the engine
        wants are plain files rather than packages.
        """
        base = Path(base)
        base.parent.mkdir(parents=True, exist_ok=True)
        bs = self.block_size

        payloads = [d for _, d, _ in self._entries]
        payloads.append(container_header(self.container_id, self._packages))
        ids = [cid for cid, _, _ in self._entries]
        ids.append(chunk_id(self.container_id, 0, CHUNK_CONTAINER_HEADER))

        ucas = bytearray()
        chunks: list[tuple[int, int]] = []
        blocks: list[tuple[int, int, int, int]] = []
        logical = 0
        for data in payloads:
            chunks.append((logical, len(data)))
            for start in range(0, max(len(data), 1), bs):
                part = data[start : start + bs]
                blocks.append((len(ucas), len(part), len(part), 0))
                ucas += part
            logical += ((len(data) + bs - 1) // bs) * bs

        dir_index = self._directory_index(
            [(n, i) for i, (_, _, n) in enumerate(self._entries) if n is not None]
        )

        toc = bytearray(TOC_MAGIC)
        toc += bytes([8, 0, 0, 0])
        toc += struct.pack(
            "<9I",
            HEADER_SIZE,
            len(payloads),
            len(blocks),
            12,
            0,
            32,
            bs,
            len(dir_index),
            1,
        )
        toc += struct.pack("<Q", self.container_id)
        toc += bytes(16)  # encryption key guid
        toc += bytes([8, 0, 0, 0])  # container flags
        toc += struct.pack("<I", 0)  # perfect hash seeds
        toc += struct.pack("<Q", 0xFFFFFFFFFFFFFFFF)  # partition size
        toc += struct.pack("<I", 0) + struct.pack("<I", 0)
        toc += bytes(HEADER_SIZE - len(toc))
        for cid in ids:
            toc += cid
        for off, ln in chunks:
            toc += off.to_bytes(5, "big") + ln.to_bytes(5, "big")
        for off, csize, usize, method in blocks:
            toc += (
                off.to_bytes(5, "little")
                + csize.to_bytes(3, "little")
                + usize.to_bytes(3, "little")
                + bytes([method])
            )
        toc += dir_index
        for data in payloads:
            toc += chunk_hash(data)

        utoc, ucas_p = base.with_suffix(".utoc"), base.with_suffix(".ucas")
        utoc.write_bytes(bytes(toc))
        ucas_p.write_bytes(bytes(ucas))
        pak = base.with_suffix(".pak")
        if pak_files:
            builder = PakWriter()
            for name, blob in pak_files.items():
                builder.add(name, blob)
            builder.write(pak)
        else:
            pak.write_bytes(_stub_pak())
        return utoc, ucas_p, pak
