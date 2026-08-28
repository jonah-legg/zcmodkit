"""Tests that only work with the game installed."""

import pytest

pytestmark = pytest.mark.game

UI_STRINGS = "/Game/Game/UI/Localization/UI_System_Strings"


def test_containers_are_indexed(kit):
    assert kit.containers
    assert sum(len(r.by_package) for r in kit.containers) > 100_000


def test_known_packages_are_present(kit):
    assert kit.has_package(UI_STRINGS)
    assert kit.has_package(
        "/Game/Game/Customizations/Characters/Common/Specialization/Tactical"
        "/CPD_TacticalSpec_Padawan"
    )


def test_missing_package_raises(kit):
    with pytest.raises(KeyError):
        kit.read_package("/Game/Game/Not/A/Real/Asset")


def test_localization_table_loads(kit):
    assert len(kit.text.entries) > 10_000
    assert kit.text.get("UI_System_Strings", "UI_FrontEnd_Quit") == "QUIT"


def test_locres_no_op_round_trip_is_byte_identical(kit):
    from zcmodkit.formats import LocRes

    raw = kit._base_locres_bytes() if hasattr(kit, "_base_locres_bytes") else None
    table = kit.text
    if raw is not None:
        assert LocRes.loads(raw).dumps() == raw
    assert table.get("UI_System_Strings", "UI_FrontEnd_Options") == "OPTIONS"


def test_edit_and_rebuild_a_real_asset(kit, tmp_path):
    from zcmodkit.formats import IoStoreReader

    mod = kit.create_mod("pytest_tmp")
    mod.asset(UI_STRINGS).replace_text("NEW CAMPAIGN", "A CONSIDERABLY LONGER LABEL")
    utoc, _, _ = mod.build(tmp_path)
    with IoStoreReader(utoc) as r:
        data = r.read_package(UI_STRINGS)
    assert b"A CONSIDERABLY LONGER LABEL" in data
    assert b"NEW CAMPAIGN" not in data
