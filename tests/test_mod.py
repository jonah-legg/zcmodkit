"""Mod naming, priority, and keeping track of what is installed."""

import pytest

from zcmodkit import InstalledMod
from zcmodkit.mod import DEFAULT_PRIORITY, Mod


class FakeKit:
    """Just enough of ModKit for tests that do not need the game."""

    def __init__(self, data=b""):
        self.data = data
        self.paks = None

    def read_package(self, path):
        return self.data


def test_default_priority_is_mid_range():
    assert 0 < DEFAULT_PRIORITY < 999


@pytest.mark.parametrize(
    ("priority", "expected"),
    [(0, "000_x_P"), (7, "007_x_P"), (100, "100_x_P"), (999, "999_x_P")],
)
def test_basename_is_zero_padded(priority, expected):
    assert Mod(FakeKit(), "x", priority).basename == expected


def test_lower_priority_sorts_first():
    """Lower number wins, so it has to sort first. Confirmed in game."""
    names = sorted(Mod(FakeKit(), "m", p).basename for p in (999, 0, 100))
    assert names[0].startswith("000")


def test_building_without_edits_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no changes"):
        Mod(FakeKit(), "empty").build(tmp_path)


@pytest.mark.parametrize(
    ("stem", "priority", "name"),
    [
        ("000_cheaper_P", 0, "cheaper"),
        ("100_hello_menu_P", 100, "hello_menu"),
        ("unprefixed_P", 999, "unprefixed"),
    ],
)
def test_installed_mod_parses_its_filename(tmp_path, stem, priority, name):
    m = InstalledMod(tmp_path / f"{stem}.utoc", [], [])
    assert m.priority == priority
    assert m.name == name
