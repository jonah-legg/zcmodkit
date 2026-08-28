"""Reading DataTables and editing values, against the real game."""

import pytest

from zcmodkit.domains import DataTable, DataTableError
from zcmodkit.formats import IoStoreReader

pytestmark = pytest.mark.game

COSTS = "/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4"
ROW_STRUCT = "AbilityCostTableRow"

#: Values written down separately in STRUCTURE.md, straight from game data.
KNOWN_AP_COSTS = {
    "BitReactor.AbilityCost.StartOfTurn": 3.0,
    "BitReactor.AbilityCost.BasicAttack": 1.0,
    "BitReactor.AbilityCost.MovementCost": 1.0,
    "BitReactor.AbilityCost.DoubleMovement": 2.0,
    "BitReactor.AbilityCost.TripleMovement": 3.0,
}


@pytest.fixture
def costs(kit):
    return DataTable(COSTS, bytearray(kit.read_package(COSTS)), row_struct=ROW_STRUCT)


def test_reads_every_row(costs):
    assert len(costs) == 39


def test_values_match_the_documented_ones(costs):
    for row, expected in KNOWN_AP_COSTS.items():
        assert costs.get(row, "ActionPointCost") == expected, row


def test_row_struct_is_resolved_without_being_told(kit):
    table = DataTable(COSTS, bytearray(kit.read_package(COSTS)))
    assert table.row_struct == ROW_STRUCT


def test_no_op_read_write_is_byte_identical(kit):
    original = kit.read_package(COSTS)
    assert (
        bytes(DataTable(COSTS, bytearray(original), row_struct=ROW_STRUCT).data)
        == original
    )


def test_setting_a_value_does_not_resize(costs):
    before = len(costs.data)
    costs.set("BitReactor.AbilityCost.BasicAttack", "ActionPointCost", 7.5)
    assert costs.get("BitReactor.AbilityCost.BasicAttack", "ActionPointCost") == 7.5
    assert len(costs.data) == before


def test_setting_one_row_leaves_the_others_alone(costs):
    costs.set("BitReactor.AbilityCost.BasicAttack", "ActionPointCost", 0.0)
    assert costs.get("BitReactor.AbilityCost.TripleMovement", "ActionPointCost") == 3.0


def test_unknown_row_and_field_raise_helpfully(costs):
    with pytest.raises(DataTableError, match="has no row"):
        costs.get("NotARow", "ActionPointCost")
    with pytest.raises(DataTableError, match="has no field"):
        costs.get("BitReactor.AbilityCost.BasicAttack", "NotAField")


def test_edits_survive_a_full_build(kit, tmp_path):
    mod = kit.create_mod("pytest_costs")
    mod.table(COSTS).set("BitReactor.AbilityCost.BasicAttack", "ActionPointCost", 0.0)
    utoc, _, _ = mod.build(tmp_path, verify=True)
    with IoStoreReader(utoc) as r:
        rebuilt = DataTable(
            COSTS, bytearray(r.read_package(COSTS)), row_struct=ROW_STRUCT
        )
    assert rebuilt.get("BitReactor.AbilityCost.BasicAttack", "ActionPointCost") == 0.0
    assert rebuilt.get("BitReactor.AbilityCost.StartOfTurn", "ActionPointCost") == 3.0
