"""Run the parser and the editor over the real game, not just fixtures.

All of this needs the game installed. These are the tests that catch anything
that only holds true for one hand-picked asset.
"""

import random

import pytest

from zcmodkit.domains import AssetEditor
from zcmodkit.formats import IoStoreReader
from zcmodkit.formats.iostore import CHUNK_EXPORT_BUNDLE_DATA, package_id
from zcmodkit.formats.zen import PackageError, ZenPackage, verify

pytestmark = pytest.mark.game

#: Kept small so the suite stays quick. Turn it up when touching the parser.
SAMPLE = 400


def _sample(kit, seed=0, n=SAMPLE):
    """Random packages out of every container, as (reader, chunk) pairs."""
    rng = random.Random(seed)
    out = []
    for r in kit.containers:
        chunks = [c for c in r.chunks if c.type == CHUNK_EXPORT_BUNDLE_DATA]
        out += [(r, c) for c in rng.sample(chunks, min(n, len(chunks)))]
    return out


def test_every_sampled_package_verifies(kit):
    """The whole game check. Real assets have to pass every invariant."""
    failures = []
    for r, chunk in _sample(kit):
        data = r.read_chunk(chunk)
        try:
            verify(data)
        except PackageError as exc:
            failures.append(f"{chunk.package_id:016x}: {exc}")
    assert not failures, "packages failed verification:\n" + "\n".join(failures[:10])


def test_corpus_contains_multi_export_packages(kit):
    """Checks the sample. One made only of single-export assets proves little."""
    counts = [len(ZenPackage(r.read_chunk(c)).exports) for r, c in _sample(kit, seed=1)]
    assert max(counts) > 1
    assert sum(1 for n in counts if n > 1) > len(counts) // 10


def test_resizing_edits_hold_up_on_multi_export_assets(kit):
    """A resize has to keep the bookkeeping straight, however many exports."""
    checked = 0
    for r, chunk in _sample(kit, seed=2, n=300):
        data = r.read_chunk(chunk)
        try:
            pkg = ZenPackage(data)
        except PackageError:
            continue
        if len(pkg.exports) < 2:
            continue

        editor = AssetEditor("/Game/Test", data)
        target = next((n for n in _ascii_strings(editor) if len(n) > 4), None)
        if target is None:
            continue

        editor.replace_text(target, target + "_MUCH_LONGER_REPLACEMENT")
        verify(editor.data)  # raises if the resize broke anything
        assert len(editor.data) == len(data) + len("_MUCH_LONGER_REPLACEMENT")
        checked += 1
        if checked >= 15:
            break
    assert checked >= 5, f"only found {checked} usable multi-export assets to edit"


def _bulk_data_package(kit):
    """A project package with a bulk data chunk alongside it, or None."""
    r = kit.containers[0]
    multi = {pid for pid, cs in r._all_by_package.items() if len(cs) > 1}
    for path, idx in r.files.items():
        if not (path.startswith("SWZeroCompany/Content/") and path.endswith(".uasset")):
            continue
        chunk = r.chunks[idx]
        if chunk.package_id in multi:
            pkg = "/Game/" + path.split("Content/", 1)[1].rsplit(".", 1)[0]
            if package_id(pkg) == chunk.package_id:
                return pkg
    return None


def test_bulk_data_is_carried_into_the_mod(kit, tmp_path):
    """About a quarter of packages own bulk data. Drop it and the asset breaks."""
    pkg = _bulk_data_package(kit)
    if pkg is None:
        pytest.skip("no bulk-data package found in the directory index")

    companions = kit.read_companions(pkg)
    assert companions, f"{pkg} should own a companion chunk"

    mod = kit.create_mod("pytest_bulk")
    mod.asset(pkg).changes = 1  # build without altering the bytes
    utoc, _, _ = mod.build(tmp_path, verify=True)

    with IoStoreReader(utoc) as r:
        types = sorted(c.type for c in r.chunks)
        assert CHUNK_EXPORT_BUNDLE_DATA in types
        assert 2 in types, f"bulk data missing from the container: {types}"
        assert r.read_package(pkg) == kit.read_package(pkg)
        rebuilt = {c.type: r.read_chunk(c) for c in r.chunks if c.type == 2}
        assert rebuilt[2] == companions[0][1]


def _ascii_strings(editor):
    """Strings in the export data that come back through find_text."""
    start, end = editor.package.export_data_range()
    blob, out, i = bytes(editor.data[start:end]), [], 0
    while i < len(blob) - 8:
        (n,) = _unpack_i32(blob, i)
        if 5 <= n <= 64 and i + 4 + n <= len(blob) and blob[i + 4 + n - 1] == 0:
            raw = blob[i + 4 : i + 4 + n - 1]
            if raw.isascii() and raw.isalnum():
                text = raw.decode()
                if len(editor.find_text(text)) == 1:
                    out.append(text)
        i += 4
    return out


def _unpack_i32(buf, at):
    import struct

    return struct.unpack_from("<i", buf, at)
