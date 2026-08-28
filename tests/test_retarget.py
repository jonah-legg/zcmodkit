"""Repointing name references, which is how a gameplay tag gets swapped."""

import pytest
from conftest import fstring, make_package

from zcmodkit.domains import AssetEditor

pytestmark = pytest.mark.game

SPECS = "/Game/Game/Customizations/Characters/Common/Specialization/Tactical/"
GATE = "br.Customization.Part.Character.Info.Name.Tel-ReaVokoss"
PRIMARY = "br.Customization.Slot.Character.Specializations.Tactical.Primary"


@pytest.fixture
def padawan(kit):
    path = SPECS + "CPD_TacticalSpec_Padawan"
    return AssetEditor(path, kit.read_package(path))


def test_the_gate_tag_is_in_the_name_map(padawan):
    assert GATE in padawan.names
    assert PRIMARY in padawan.names


def test_an_ordinary_class_has_no_gate(kit):
    soldier = AssetEditor(
        SPECS + "CPD_TacticalSpec_Soldier",
        kit.read_package(SPECS + "CPD_TacticalSpec_Soldier"),
    )
    assert GATE not in soldier.names


def test_retarget_changes_exactly_one_reference(padawan):
    before = len(padawan.data)
    padawan.retarget_name(GATE, PRIMARY, expect=1)
    assert padawan.changes == 1
    assert len(padawan.data) == before, "retargeting must not resize the asset"


def test_retarget_keeps_the_package_valid(padawan):
    from zcmodkit.formats.zen import verify

    padawan.retarget_name(GATE, PRIMARY)
    verify(padawan.data)


def test_wrong_expected_count_raises(padawan):
    with pytest.raises(ValueError, match="expected 5"):
        padawan.retarget_name(GATE, PRIMARY, expect=5)


def test_unknown_names_raise_clearly(padawan):
    with pytest.raises(KeyError, match="not in the name map"):
        padawan.retarget_name("not.a.real.tag", PRIMARY)
    with pytest.raises(KeyError, match="cannot be added yet"):
        padawan.retarget_name(GATE, "not.a.real.tag")


def test_replace_text_points_at_retarget_for_name_map_strings(padawan):
    with pytest.raises(KeyError, match="retarget_name"):
        padawan.replace_text(GATE, "something else")


@pytest.mark.parametrize("_unused", [None])
def test_editor_works_without_a_game(_unused):
    """The synthetic path, so this file is not entirely game dependent."""
    editor = AssetEditor("/Game/Test", make_package(fstring("HELLO"), names=("A", "B")))
    assert editor.names == ["A", "B"]
