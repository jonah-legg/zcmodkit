"""Read and edit Unreal .locres text tables.

Edits copy the original index bytes through untouched, every namespace, key and
hash of them. Only the string array on the end gets rebuilt, and a key is moved
by patching its 4-byte string index. That way none of this depends on knowing
Unreal's string hash.
"""

from __future__ import annotations

import io
import struct

MAGIC = bytes.fromhex("0e147475674a03fc4a15909dc3377f1b")
NUL = bytes([0])


def _rstr(st: io.BytesIO) -> str:
    (n,) = struct.unpack("<i", st.read(4))
    if n == 0:
        return ""
    if n < 0:
        return st.read(-n * 2).decode("utf-16-le").rstrip(chr(0))
    return st.read(n).decode("latin-1").rstrip(chr(0))


def _wstr(s: str) -> bytes:
    """Write an FString. Falls back to UTF-16 if the text is not ASCII."""
    if s.isascii():
        raw = s.encode("ascii") + NUL
        return struct.pack("<i", len(raw)) + raw
    raw = s.encode("utf-16-le") + NUL * 2
    return struct.pack("<i", -(len(raw) // 2)) + raw


class LocRes:
    """A text table keyed by (namespace, key)."""

    def __init__(self) -> None:
        self._data = bytearray()
        self._array_offset = 0
        self._strings: list[str] = []
        self._refs: list[int] = []
        self._slots: dict[tuple[str, str], tuple[int, int]] = {}

    @classmethod
    def loads(cls, data: bytes) -> LocRes:
        """Parse a .locres file."""
        self = cls()
        self._data = bytearray(data)
        b = io.BytesIO(data)
        if b.read(16) != MAGIC:
            raise ValueError("not a .locres file")
        self.version = b.read(1)[0]
        (self._array_offset,) = struct.unpack("<q", b.read(8))
        if self.version >= 3:
            b.read(4)
        (ns_count,) = struct.unpack("<I", b.read(4))

        for _ in range(ns_count):
            b.read(4)
            ns = _rstr(b)
            (key_count,) = struct.unpack("<I", b.read(4))
            for _ in range(key_count):
                b.read(4)
                key = _rstr(b)
                b.read(4)  # source string hash
                at = b.tell()  # byte offset of the string index
                (idx,) = struct.unpack("<i", b.read(4))
                self._slots[(ns, key)] = (idx, at)

        sb = io.BytesIO(data)
        sb.seek(self._array_offset)
        (count,) = struct.unpack("<i", sb.read(4))
        for _ in range(count):
            self._strings.append(_rstr(sb))
            self._refs.append(
                struct.unpack("<i", sb.read(4))[0] if self.version >= 3 else 1
            )
        # Hang on to the shipped array bytes so edits only ever append.
        self._shipped_count = count
        self._shipped_body = bytes(data[self._array_offset + 4 : sb.tell()])
        self._trailing = bytes(data[sb.tell() :])
        return self

    @property
    def entries(self) -> dict[tuple[str, str], str]:
        """Every (namespace, key) to text pair."""
        return {
            k: self._strings[i]
            for k, (i, _) in self._slots.items()
            if 0 <= i < len(self._strings)
        }

    def get(self, namespace: str, key: str) -> str | None:
        """Look one entry up."""
        slot = self._slots.get((namespace, key))
        if slot is None or not 0 <= slot[0] < len(self._strings):
            return None
        return self._strings[slot[0]]

    def find(self, text: str) -> list[tuple[str, str, str]]:
        """Every entry whose text is exactly `text`."""
        return [(ns, k, v) for (ns, k), v in self.entries.items() if v == text]

    def set(self, namespace: str, key: str, value: str) -> None:
        """Point an entry at `value`, adding it to the string array if it is new."""
        slot = self._slots.get((namespace, key))
        if slot is None:
            raise KeyError(f"{namespace} / {key} is not in this table")
        try:
            idx = self._strings.index(value)
        except ValueError:
            self._strings.append(value)
            self._refs.append(0)
            idx = len(self._strings) - 1
        old_idx, at = slot
        if 0 <= old_idx < len(self._refs):
            self._refs[old_idx] = max(0, self._refs[old_idx] - 1)
        self._refs[idx] += 1
        self._slots[(namespace, key)] = (idx, at)
        struct.pack_into("<i", self._data, at, idx)

    def dumps(self) -> bytes:
        """Write it back out as .locres bytes.

        The header and index are the original bytes with only string indices
        moved. The string array gets rebuilt. Since the array is last in the
        file its length can change without disturbing anything.
        """
        out = bytearray(self._data[: self._array_offset])
        out += struct.pack("<i", len(self._strings))
        out += self._shipped_body
        for i in range(self._shipped_count, len(self._strings)):
            out += _wstr(self._strings[i])
            if self.version >= 3:
                out += struct.pack("<i", self._refs[i])
        out += self._trailing
        return bytes(out)
