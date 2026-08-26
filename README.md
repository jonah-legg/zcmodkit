# ZeroCompany ModKit

A Python toolkit for creating and installing mods for Zero Company with the intent of keeping the process as simple as possible.

## Install

```bash
pip install zcmodkit
```

## Quick Start

```python
import zcmodkit

kit = zcmodkit.open()
mod = kit.create_mod("no_respec")
mod.operatives.all.disable_respec()
mod.install()
```

This is the pattern of all mods: open, create, edit, install.

## Core Concepts

### Opening the Kit

```python
kit = zcmodkit.open()                          # auto-detects Steam/Epic install
kit = zcmodkit.open("D:/Games/ZeroCompany")    # explicit path
```

Returns a `ModKit` object, a read-only interface to the game's data and the entry point for creating mods.

### Creating a Mod

```python
mod = kit.create_mod("no_respec")
```

### Installing

```python
mod.install()                   # build and place into game's mod folder
```

## Making Changes

### Operatives

```python
mod.operatives.all                  # target every operative
mod.operatives.hawks                # target Hawks 
mod.operatives.trick                # target Trick
```

Each returns a handle with domain-specific methods:

```python
mod.operatives.hawks.set_health(200)
mod.operatives.hawks.set_movement(8)
mod.operatives.hawks.disable_respec()
```

Use `.all` to apply across every operative:

```python
mod.operatives.all.disable_respec()
```

### Weapons

```python
mod.weapons.dc15a.set_damage(45)
mod.weapons.dc15a.set_range(12)
```

### Abilities

```python
mod.abilities.grapple.set_cooldown(1)
mod.abilities.overwatch.set_range(15)
```

### Direct Table Access

This tool is not all-encompassing, and there will be fields that aren't accessible through the abstracted layer. For advanced users that want to have more granular access, you can edit the tables directly:

```python
mod.table("DT_OperativeBaseStats").set("Hawks", "MaxHP", 200)
mod.table("DT_OperativeBaseStats").set_all("bCanRespec", False)
mod.table("DT_MissionRewards").multiply("*", "XPGained", 2.0)
mod.table("DT_SomeTable").add("RowName", "SomeInt", 10)
```

To discover table and field names:

```python
kit.tables()                                     
kit.table("DT_OperativeBaseStats").rows()        
kit.table("DT_OperativeBaseStats").row("Hawks")  
```

## Other Features

### Building Without Installing

```python
mod.build("./output")
```

This builds the .pak without installing it in your game.

### Sharing a Mod as a Recipe

To create a recipe:

```python
import zcmodkit

kit = zcmodkit.open()
mod = kit.create_mod("hardcore")
mod.operatives.all.set_health(60)
mod.operatives.all.disable_respec()
mod.export("hardcore.json")
```

To install a recipe:

```python
import zcmodkit
zcmodkit.open().install("hardcore.json")
```

### Uninstalling a Mod

Just delete the mod's `.pak` file. The base game is never modified.

## Requirements

- Python 3.10+
- Zero Company installed via Steam or Epic
