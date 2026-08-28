"""Oodle decompression, for reading compressed entries out of the game's paks."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

_SEARCH_NAMES = ("oodle-data-shared.dll", "oo2core_9_win64.dll", "oo2core_8_win64.dll")
_lib = None
_fn = None


def _candidates() -> list[Path]:
    """The usual places an Oodle DLL turns up."""
    out: list[Path] = []
    env = os.environ.get("ZCMODKIT_OODLE")
    if env:
        out.append(Path(env))
    for base in (Path.cwd(), Path(__file__).parent, Path.home() / "Downloads"):
        out.extend(base / name for name in _SEARCH_NAMES)
    # FModel keeps one in its Output/.data folder
    out.extend((Path.home() / "Downloads").glob("*/Output/.data/oodle-data-shared.dll"))
    return out


def load(path: str | os.PathLike | None = None):
    """Load the Oodle DLL and hand back its decompress function."""
    global _lib, _fn
    if _fn is not None and path is None:
        return _fn
    tried = [Path(path)] if path else _candidates()
    for p in tried:
        if not p.is_file():
            continue
        lib = ctypes.CDLL(str(p))
        fn = lib.OodleLZ_Decompress
        fn.restype = ctypes.c_ssize_t
        fn.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ssize_t,
            ctypes.c_void_p,
            ctypes.c_ssize_t,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ssize_t,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ssize_t,
            ctypes.c_int,
        ]
        _lib, _fn = lib, fn
        return fn
    raise FileNotFoundError(
        "Could not find an Oodle DLL. Set ZCMODKIT_OODLE to the full path of "
        "oodle-data-shared.dll (FModel ships one in its Output/.data folder)."
    )


def decompress(
    data: bytes, out_size: int, dll: str | os.PathLike | None = None
) -> bytes:
    """Decompress one Oodle block."""
    fn = load(dll)
    dst = ctypes.create_string_buffer(out_size)
    n = fn(data, len(data), dst, out_size, 1, 0, 0, None, 0, None, None, None, 0, 3)
    if n != out_size:
        raise RuntimeError(f"Oodle decompress failed: got {n}, expected {out_size}")
    return dst.raw[:out_size]
