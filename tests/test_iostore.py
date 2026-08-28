"""IoStore containers, out and back again. No game install needed."""

import struct

from zcmodkit.formats import (
    IoStoreReader,
    IoStoreWriter,
    chunk_hash,
    chunk_id,
    package_id,
)
from zcmodkit.formats.iostore import CHUNK_CONTAINER_HEADER, TOC_MAGIC


def test_package_id_is_cityhash_of_lowercased_utf16():
    # Checked against a container from a community mod that works.
    pkg = "/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4"
    assert package_id(pkg) == 0x0C4690E9362CBAF0


def test_package_id_is_case_insensitive():
    assert package_id("/Game/Foo/Bar") == package_id("/game/foo/BAR")


def test_chunk_id_layout():
    cid = chunk_id(0x1122334455667788, index=0, chunk_type=CHUNK_CONTAINER_HEADER)
    assert len(cid) == 12
    assert struct.unpack_from("<Q", cid)[0] == 0x1122334455667788
    assert cid[11] == CHUNK_CONTAINER_HEADER


def test_chunk_hash_is_blake3_160_padded():
    h = chunk_hash(b"hello")
    assert len(h) == 24
    assert h[20:] == bytes(4)


def test_write_then_read_round_trip(tmp_path):
    payload = b"cooked package bytes" * 100
    pkg = "/Game/Game/Test/Asset"
    w = IoStoreWriter(container_id=package_id("/zcmodkit/test"))
    w.add_package(pkg, payload)
    utoc, _ucas, pak = w.write(tmp_path / "000_test_P")

    assert utoc.read_bytes()[:16] == TOC_MAGIC
    assert pak.stat().st_size > 0  # stub pak must exist
    with IoStoreReader(utoc) as r:
        assert r.header.version == 8
        assert r.mount_point == "../../../"
        assert r.read_package(pkg) == payload
        assert "Asset.uasset" in r.files


def test_multiple_packages_round_trip(tmp_path):
    pkgs = {
        f"/Game/Game/Test/Asset{i}": bytes([i]) * (1000 * (i + 1)) for i in range(4)
    }
    w = IoStoreWriter(container_id=1234)
    for path, data in pkgs.items():
        w.add_package(path, data)
    utoc, _, _ = w.write(tmp_path / "000_multi_P")
    with IoStoreReader(utoc) as r:
        for path, data in pkgs.items():
            assert r.read_package(path) == data


def test_payload_larger_than_one_block(tmp_path):
    payload = bytes(range(256)) * 1000  # ~256 KB, spans several 64 KB blocks
    w = IoStoreWriter(container_id=99)
    w.add_package("/Game/Game/Test/Big", payload)
    utoc, _, _ = w.write(tmp_path / "000_big_P")
    with IoStoreReader(utoc) as r:
        assert r.read_package("/Game/Game/Test/Big") == payload
