# ZeroCompany ModKit

An unofficial Python toolkit for building and installing mods for Star Wars: Zero Company. The goal is to keep modding down to a few lines of Python instead of a pile of tools.

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

# ...and some on screen text, in the same mod.
mod.asset("/Game/Game/UI/Localization/UI_System_Strings").replace_text(
    "NEW CAMPAIGN", "NEW MODDED CAMPAIGN"
)

mod.install()
```

Launch the game. Basic attacks are free and the main menu button reads differently. Every mod follows that shape: open the game, create a mod, edit some things, install.

## Core Concepts

### Opening the kit

```python
kit = zcmodkit.open()  # finds Steam and Epic on its own
kit = zcmodkit.open("D:/Games/Star Wars Zero Company")
```

A `ModKit` reads the installed game and never writes to it. It is where mods come from.

### Finding things

```python
kit.has_package("/Game/Game/UI/Localization/UI_System_Strings")  # True
kit.read_package(path)          # the raw cooked bytes
kit.text.find("CONTINUE")       # [(namespace, key, value), ...]
```

`kit.text` is the game's shipped text table. It is usually the fastest way to get from something you saw on screen to the asset it came from.

### Editing text

```python
asset = mod.asset("/Game/Game/UI/Localization/UI_System_Strings")
asset.replace_text("QUIT", "RUN AWAY")
```

The replacement can be any length. The asset gets resized and its export table fixed up for you.

### Editing values

Most of the game's tuning lives in DataTables. Ability costs, weapon stats, upgrade curves. Open one by its package path and set fields by row and name:

```python
costs = mod.table("/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4")

costs.get("BitReactor.AbilityCost.BasicAttack", "ActionPointCost")  # 1.0
costs.set("BitReactor.AbilityCost.BasicAttack", "ActionPointCost", 0.0)
costs.set_all("AdvantageCost", 0.0)  # every row that has the field
```

To look around a table before changing anything:

```python
len(costs)        # how many rows
list(costs.rows)  # row names
costs.row("BitReactor.AbilityCost.BasicAttack").keys()  # field names
```

Cooked assets do not record property names, so this needs the schemas for the build you are modding. They ship with zcmodkit and there is nothing to download. If a patch moves a struct around, the walk stops landing exactly on the end of the asset and the edit is refused instead of written to the wrong offset. A stale mappings file gives you a clear error, never a quietly wrong value. Text edits do not use mappings and keep working either way.

### Editing gameplay tags

Tags are everywhere in this game, and a lot of what looks like hardcoded behaviour is really a tag sitting in a container. You can take one out or put one in:

```python
spec = mod.asset(".../CPD_TacticalSpec_Padawan")
spec.names  # every name the package refers to

spec.remove_gameplay_tag("br.Customization.Part.Character.Info.Name.Tel-ReaVokoss", expect=1)

spec.add_gameplay_tag(
    beside="br.Customization.Part.Character.Class.Default",
    tag="br.Customization.Part.Character.Info.Name.Tel-ReaVokoss",
)
```

Containers are not labelled in cooked data, so `add_gameplay_tag` wants a tag that is already in the one you mean. `expect` says how many containers you think should change, and it is worth setting whenever you know.

If you would rather not resize anything, you can point a reference at a different name the package already uses:

```python
spec.retarget_name(gate_tag, slot_tag, expect=1)
```

That leaves the asset exactly the same size, though the container keeps its original length, which some of the game's checks do care about.

### Referencing other assets

Sometimes an asset needs to point at something it has never heard of. That means adding an import, which grows the header, renumbers existing references and updates the container. All of that is handled for you:

```python
view_model = mod.asset(".../BP_SpecializationSelectionVM")

padawan = ".../CPD_TacticalSpec_Padawan"
key = view_model.add_import(padawan, kit.public_export_hash(padawan))
```

Then you can use that import wherever object references live. Maps of object to object can be found by what they hold, and grown:

```python
mapping = view_model.find_object_map(entries=8, referencing="CPD_TacticalSpec_Scout")
mapping.named_entries       # see what is in it before touching anything
mapping.append(key, value)  # or append(key, None) for a null
```

`find_object_map` raises unless exactly one map matches, so an edit never lands on a lucky second candidate.

### Installing

```python
mod.install()       # build and copy into the game's ~mods folder
mod.build("./out")  # build without installing
mod.uninstall()     # take it back out
```

Installing writes three files into `SWZeroCompany/Content/Paks/~mods/`, a `.utoc`, a `.ucas` and a small `.pak`. The base game is never touched, and uninstalling is just deleting them.

## Load Order

When two mods edit the same asset, only one of them loads. **Lower priority wins.**

```python
kit.create_mod("overrides_everything", priority=0)  # 000_overrides_everything_P
kit.create_mod("ordinary")                          # 100_ordinary_P (the default)
kit.create_mod("last_resort", priority=999)         # 999_last_resort_P
```

To see what is installed and whether anything is being shadowed:

```python
for mod in kit.installed_mods():  # best priority first
    print(mod.priority, mod.name, mod.assets)

for asset, mods in kit.conflicts().items():
    print(f"{asset}: {mods[0].name} wins over {[m.name for m in mods[1:]]}")
```

## Things That Will Trip You Up

These took a long time to work out, so they are worth reading before you spend an evening on a mod that never loads.

**Every mod needs a package with no imports in it.** A container where all of the packages have imports has never loaded in this game, and adding one spare package with none fixes it. Nobody has worked out why yet. Ship something harmless alongside your real edits:

```python
mod.asset("/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4")  # unchanged, just present
```

**Characters are written into the save when they join.** Anything you change about a character's customization only reaches characters built after your mod is installed. New campaigns and new recruits pick it up. The squad you already have will not.

**Some things are read from the asset and some are not.** What the specialisation picker offers comes from a copy of the data cached in `AssetRegistry.bin`, so editing `AllowedSlots` on a part does nothing whatsoever. Display names, tags and abilities do come from the asset. If an edit looks correct and changes nothing, that is usually why.

**Check your work before launching.** `mod.build(verify=True)` parses every package again and refuses to ship a broken one, which beats hearing about it from a game that will not start.

## Examples

The `examples/` folder has working mods you can run as they are:

| File | What it does |
| --- | --- |
| `mod_test_poc.py` | Changes a main menu button. The smallest useful mod. |
| `cheaper_actions.py` | Drops ability costs in a DataTable. |
| `classes_unlocked.py` | Opens up the Jedi and Mandalorian specialisations for everyone. |

## Requirements

* Python 3.10+
* Star Wars: Zero Company installed via Steam or Epic

## Disclaimer

ZeroCompany ModKit is an independent, community driven project and is not affiliated with, endorsed by, or sponsored by Electronic Arts (EA), Respawn Entertainment, or any of their subsidiaries. Star Wars: Zero Company and all related trademarks are the property of their respective owners. This project is built by fans, for fans, and exists solely to support the modding community.
