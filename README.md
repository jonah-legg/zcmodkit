# ZeroCompany ModKit

An unofficial Python toolkit for creating and installing mods for Star Wars: Zero Company, with the intent of keeping the process as simple as possible.

## Install

```bash
pip install zcmodkit
```

## Quick Start

```python
import zcmodkit

kit = zcmodkit.open()
mod = kit.create_mod("hello_menu")

# Change a value in one of the game's data tables.
mod.table("/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4").set(
    "BitReactor.AbilityCost.BasicAttack", "ActionPointCost", 0.0
)

# ...and some on-screen text, in the same mod.
mod.asset("/Game/Game/UI/Localization/UI_System_Strings").replace_text(
    "NEW CAMPAIGN", "NEW MODDED CAMPAIGN"
)

mod.install()
```

Launch the game; basic attacks are free and the main menu button reads differently. This is the pattern of all mods: open, create, edit, install.

## Core Concepts

### Opening the Kit

```python
kit = zcmodkit.open()  # auto-detects Steam/Epic
kit = zcmodkit.open("D:/Games/Star Wars Zero Company")
```

A `ModKit` is a read-only view of the installed game and the entry point for creating mods.

### Finding things

```python
kit.has_package("/Game/Game/UI/Localization/UI_System_Strings")  # True
kit.read_package(path)  # raw cooked bytes
kit.text.find("CONTINUE")  # [(namespace, key, value), ...] from the game's text table
```

`kit.text` is the shipped localization table. It is the quickest way to find a piece of on-screen text and the asset it belongs to.

### Editing assets

```python
asset = mod.asset("/Game/Game/UI/Localization/UI_System_Strings")
asset.replace_text("QUIT", "RUN AWAY")  # any length
```

Gameplay tags, class names and object paths are not text in the export data - they live in the package's name map, and the asset refers to them by index. Repoint one at another name the package already uses:

```python
spec = mod.asset(".../CPD_TacticalSpec_Padawan")
spec.names  # every name the package refers to
spec.retarget_name(gate_tag, slot_tag, expect=1)
```

Nothing is resized and no name is added, so the asset stays exactly the same size. `expect` asserts how many references should change, which is worth setting when you know.

### Editing values

Most of the game's tuning lives in DataTables: ability costs, weapon stats, upgrade curves. Open one by its package path and set fields by row and name:

```python
costs = mod.table("/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4")

costs.get("BitReactor.AbilityCost.BasicAttack", "ActionPointCost")  # 1.0
costs.set("BitReactor.AbilityCost.BasicAttack", "ActionPointCost", 0.0)
costs.set_all("AdvantageCost", 0.0)  # every row that has the field
```

To find your way around a table before changing anything:

```python
len(costs)  # how many rows
list(costs.rows)  # row names
costs.row("BitReactor.AbilityCost.BasicAttack").keys()  # field names
```

Numbers are fixed width, so setting one never moves anything else in the asset.

Cooked assets do not record property names, so this needs the schemas for the build you are modding. Those ship with zcmodkit, and there is nothing to download. If the game is patched and a struct's layout changes, the table walk stops landing exactly on the end of the asset and the edit is refused rather than written to the wrong offset. Thus, a stale mappings file produces a clear error, never a silently wrong value. Text edits do not use mappings and keep working regardless.

### Installing

```python
mod.install()  # build and copy into the game's ~mods folder
mod.build("./out")  # build without installing
mod.uninstall()  # remove it again
```

Installing writes three files - `.utoc`, `.ucas` and a stub `.pak` - into
`SWZeroCompany/Content/Paks/~mods/`. The base game is never modified.

## Load Order

When two mods edit the same asset, only one of them is loaded. **Lower priority wins.**

```python
kit.create_mod("overrides_everything", priority=0)  # 000_overrides_everything_P
kit.create_mod("ordinary")  # 100_ordinary_P  (the default)
kit.create_mod("last_resort", priority=999)  # 999_last_resort_P
```

To see what is installed and whether anything is being shadowed:

```python
for mod in kit.installed_mods():  # best priority first
    print(mod.priority, mod.name, mod.assets)

for asset, mods in kit.conflicts().items():
    print(f"{asset}: {mods[0].name} wins over {[m.name for m in mods[1:]]}")
```

## Requirements

- Python 3.10+
- Star Wars: Zero Company installed via Steam or Epic

## Disclaimer

ZeroCompany ModKit is an independent, community-driven project and is not affiliated with, endorsed by, or sponsored by Electronic Arts (EA), Respawn Entertainment, or any of their subsidiaries. Star Wars: Zero Company and all related trademarks are the property of their respective owners. This project is built by fans, for fans, and exists solely to support the modding community.
