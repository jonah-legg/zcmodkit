"""Finding where Zero Company is installed."""

from __future__ import annotations

import os
from pathlib import Path

_RELATIVE_PAKS = Path("SWZeroCompany") / "Content" / "Paks"

_COMMON_ROOTS = [
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Star Wars Zero Company"),
    Path(r"C:\Program Files\Epic Games\Star Wars Zero Company"),
]


def _steam_libraries() -> list[Path]:
    """Check Steam's libraryfolders.vdf for games on other drives."""
    vdf = Path(r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf")
    out: list[Path] = []
    if not vdf.is_file():
        return out
    for line in vdf.read_text(encoding="utf-8", errors="ignore").splitlines():
        if '"path"' in line:
            parts = line.split('"')
            if len(parts) >= 4:
                out.append(
                    Path(parts[3]) / "steamapps" / "common" / "Star Wars Zero Company"
                )
    return out


def find_install(explicit: str | os.PathLike | None = None) -> Path:
    """The game root, meaning the folder that holds SWZeroCompany/."""
    if explicit:
        root = Path(explicit)
        if not (root / _RELATIVE_PAKS).is_dir():
            raise FileNotFoundError(f"No {_RELATIVE_PAKS} under {root}")
        return root
    env = os.environ.get("ZCMODKIT_GAME")
    candidates = ([Path(env)] if env else []) + _COMMON_ROOTS + _steam_libraries()
    for root in candidates:
        if (root / _RELATIVE_PAKS).is_dir():
            return root
    raise FileNotFoundError(
        "Could not find Star Wars Zero Company. Pass the path explicitly, "
        "e.g. zcmodkit.open(r'D:/Games/Star Wars Zero Company')."
    )


def paks_dir(root: Path) -> Path:
    """Where the Paks live under a game root."""
    return root / _RELATIVE_PAKS
