"""Small reader and writer for UE4 and UE5 .pak archives, version 11, no encryption."""

from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import dataclass
from pathlib import Path

from . import oodle

PAK_MAGIC = 0x5A6F12E1
NUL = bytes([0])


def _rstr(st: io.BytesIO) -> str:
    """Read an FString."""
    (n,) = struct.unpack("<i", st.read(4))
    if n == 0:
        return ""
    if n < 0:
        return st.read(-n * 2).decode("utf-16-le").rstrip(chr(0))
    return st.read(n).decode("latin-1").rstrip(chr(0))


def _wstr(s: str) -> bytes:
    """Write an FString. ASCII, null terminated."""
    raw = s.encode("latin-1") + NUL
    return struct.pack("<i", len(raw)) + raw


@dataclass
class Entry:
    """One file inside a pak."""

    path: str
    offset: int
    size: int
    uncompressed_size: int
    compression_index: int
    block_count: int


class PakReader:
    """Reads a .pak index and pulls files back out."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._f = open(self.path, "rb")  # noqa: SIM115, closed by close()/__exit__
        self.entries: dict[str, Entry] = {}
        self._read_index()

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _read_index(self) -> None:
        f = self._f
        f.seek(0, 2)
        size = f.tell()
        tail_len = min(4096, size)
        f.seek(size - tail_len)
        tail = f.read(tail_len)
        h = tail.rfind(struct.pack("<I", PAK_MAGIC))
        if h < 0:
            raise ValueError(f"{self.path.name}: not a pak file (no magic)")
        (self.version,) = struct.unpack_from("<i", tail, h + 4)
        idx_off, idx_size = struct.unpack_from("<qq", tail, h + 8)

        f.seek(idx_off)
        idx = io.BytesIO(f.read(idx_size))
        self.mount_point = _rstr(idx)
        idx.read(4 + 8)  # NumEntries, PathHashSeed
        if struct.unpack("<i", idx.read(4))[0]:
            idx.read(36)  # path hash index offset/size/hash
        fdi_off = fdi_size = None
        if struct.unpack("<i", idx.read(4))[0]:
            fdi_off, fdi_size = struct.unpack("<qq", idx.read(16))
            idx.read(20)
        (enc_size,) = struct.unpack("<i", idx.read(4))
        encoded = idx.read(enc_size)
        if fdi_off is None:
            raise ValueError("pak has no full directory index; unsupported")

        f.seek(fdi_off)
        fdi = io.BytesIO(f.read(fdi_size))
        (ndirs,) = struct.unpack("<i", fdi.read(4))
        for _ in range(ndirs):
            d = _rstr(fdi)
            (nfiles,) = struct.unpack("<i", fdi.read(4))
            for _ in range(nfiles):
                name = _rstr(fdi)
                (eo,) = struct.unpack("<i", fdi.read(4))
                self.entries[d + name] = self._decode(d + name, encoded, eo)

    @staticmethod
    def _decode(path: str, buf: bytes, at: int) -> Entry:
        """Unpack one bit-packed index entry."""
        (v,) = struct.unpack_from("<I", buf, at)
        p = at + 4
        cmi = (v >> 23) & 0x3F
        fmt = "<I" if v & (1 << 31) else "<q"
        (offset,) = struct.unpack_from(fmt, buf, p)
        p += 4 if v & (1 << 31) else 8
        fmt = "<I" if v & (1 << 30) else "<q"
        (usize,) = struct.unpack_from(fmt, buf, p)
        p += 4 if v & (1 << 30) else 8
        if cmi:
            fmt = "<I" if v & (1 << 29) else "<q"
            (size,) = struct.unpack_from(fmt, buf, p)
        else:
            size = usize
        return Entry(path, offset, size, usize, cmi, (v >> 6) & 0xFFFF)

    def read(self, path: str) -> bytes:
        """Pull one file out of the pak, decompressing it if it needs it."""
        e = self.entries.get(path)
        if e is None:
            raise KeyError(path)
        f = self._f
        f.seek(e.offset)
        head = f.read(64 + e.block_count * 16 + 32)
        # header: Offset, Size, UncompressedSize, CompressionMethodIndex,
        #         Hash, [blocks], Flags, BlockSize
        p = 24
        (cmi,) = struct.unpack_from("<i", head, p)
        p += 4
        p += 20
        blocks = []
        if cmi:
            (nb,) = struct.unpack_from("<i", head, p)
            p += 4
            for _ in range(nb):
                s, t = struct.unpack_from("<qq", head, p)
                p += 16
                blocks.append((s, t))
        p += 1
        (block_size,) = struct.unpack_from("<i", head, p)
        p += 4

        if not cmi:
            f.seek(e.offset + p)
            return f.read(e.size)

        out = bytearray()
        base = e.offset if blocks and blocks[0][0] < e.offset else 0
        for s, t in blocks:
            f.seek(base + s)
            comp = f.read(t - s)
            want = min(block_size, e.uncompressed_size - len(out))
            out += oodle.decompress(comp, want)
        return bytes(out)


class PakWriter:
    """Builds a version 11 pak, uncompressed and unencrypted."""

    VERSION = 11
    MOUNT_POINT = "../../../"

    def __init__(self):
        self._files: dict[str, bytes] = {}

    def add(self, path: str, data: bytes) -> None:
        """Queue up a file at an in-pak path like 'SWZeroCompany/Content/...'."""
        self._files[path.replace("\\", "/")] = data

    @staticmethod
    def _header(offset: int, size: int, sha: bytes) -> bytes:
        # UnrealPak puts 0 in the inline header Offset field, not the real one.
        del offset
        return (
            struct.pack("<qqq", 0, size, size)
            + struct.pack("<i", 0)
            + sha
            + bytes([0])
            + struct.pack("<i", 0)
        )

    @staticmethod
    def _encoded(offset: int, size: int) -> bytes:
        flags = 0
        if offset <= 0xFFFFFFFF:
            flags |= 1 << 31
        if size <= 0xFFFFFFFF:
            flags |= 1 << 30
        out = struct.pack("<I", flags)
        out += struct.pack("<I" if offset <= 0xFFFFFFFF else "<q", offset)
        out += struct.pack("<I" if size <= 0xFFFFFFFF else "<q", size)
        return out

    def write(self, dest: str | Path) -> Path:
        """Write the pak out and give back its path."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = bytearray()
        encoded = bytearray()
        offsets: dict[str, int] = {}
        for path, data in self._files.items():
            offset = len(body)
            sha = hashlib.sha1(data).digest()
            body += self._header(offset, len(data), sha) + data
            offsets[path] = len(encoded)
            encoded += self._encoded(offset, len(data))

        # full directory index: {directory: {filename: encoded entry offset}}
        dirs: dict[str, dict[str, int]] = {}
        for path in self._files:
            d, _, name = path.rpartition("/")
            dirs.setdefault(d + "/", {})[name] = offsets[path]
        fdi = bytearray(struct.pack("<i", len(dirs)))
        for d, files in dirs.items():
            fdi += _wstr(d) + struct.pack("<i", len(files))
            for name, eo in files.items():
                fdi += _wstr(name) + struct.pack("<i", eo)

        index_offset = len(body)
        fdi_offset = index_offset  # patched below once primary size is known
        primary = bytearray()
        primary += _wstr(self.MOUNT_POINT)
        primary += struct.pack("<i", len(self._files))
        primary += struct.pack("<Q", 0)  # path hash seed
        primary += struct.pack("<i", 0)  # no path hash index
        primary += struct.pack("<i", 1)  # has full directory index
        fdi_ptr = len(primary)
        primary += struct.pack("<qq", 0, len(fdi)) + bytes(20)
        primary += struct.pack("<i", len(encoded)) + bytes(encoded)
        primary += struct.pack("<i", 0)  # no non-encoded entries

        fdi_offset = index_offset + len(primary)
        struct.pack_into("<q", primary, fdi_ptr, fdi_offset)
        struct.pack_into("<qq", primary, fdi_ptr, fdi_offset, len(fdi))
        primary[fdi_ptr + 16 : fdi_ptr + 36] = hashlib.sha1(bytes(fdi)).digest()

        out = bytes(body) + bytes(primary) + bytes(fdi)
        footer = bytes(16) + bytes([0])
        footer += struct.pack("<I", PAK_MAGIC) + struct.pack("<i", self.VERSION)
        footer += struct.pack("<qq", index_offset, len(primary))
        footer += hashlib.sha1(bytes(primary)).digest()
        footer += bytes(32 * 5)
        dest.write_bytes(out + footer)
        return dest
