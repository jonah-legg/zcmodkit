"""Open up the specialisations the game keeps to one character each.

    python examples/classes_unlocked.py

Padawan and Wayseeker belong to Tel-Rea Vokoss. Warrior and Combat Jump belong
to Cly Kullervo. Each is held back the same way: the part lists a tag in
AllowedSlots that only its owner carries, and the game offers a part only when
the slot carries every tag the part asks for.

The fix has to happen on the character side. What the picker offers comes from
the copy of AllowedSlots cached in AssetRegistry.bin, not from the asset, so
editing the part changes nothing at all. Handing every character the name tags
those parts ask for does work, and that is what this does, adding them to the
name parts next to the character's own.

BP_SpecializationSelectionVM also holds a map of primary specialisation to
secondary. A class the map does not mention has nothing to pair with, so
Padawan gets an entry and Warrior gets one with no secondary, which is what
Cly's own definition does.

Worth knowing before you run it: a character's customization is written into
the save when they join, so this only reaches characters built afterwards. New
campaigns and new recruits pick it up. The squad you already have will not.
"""

import zcmodkit
from zcmodkit.formats.iostore import package_id

TACTICAL = "/Game/Game/Customizations/Characters/Common/Specialization/Tactical/"
VIEW_MODEL = (
    "/Game/Game/UI/Strategy/Personnel/FocusTree/BP/BP_SpecializationSelectionVM"
)

#: The tags the locked classes ask for. Give these to a character and the
#: classes their owners hold become available.
WANTED = (
    "br.Customization.Part.Character.Info.Name.Tel-ReaVokoss",
    "br.Customization.Part.Character.Info.Name.ClyKullervo",
)

#: Where a character's own name tag lives.
NAME_PREFIX = "br.Customization.Part.Character.Info.Name."

#: Every container that has loaded in this game holds at least one package with
#: no imports, and one where everything has imports has never loaded. Why is
#: not worked out, so each mod carries a spare package to stay on the side that
#: works. These ship unchanged and do nothing else.
ANCHOR_A = "/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4"
ANCHOR_B = "/Game/Game/FX/Data/STRUCT_FX_DS_Destroy"

kit = zcmodkit.open()


def name_parts():
    """Every CPD_H_Name_* package, by its /Game/... path."""
    for reader in kit.containers:
        for filename in reader.files:
            base = filename.rsplit("/", 1)[-1]
            if not base.startswith("CPD_H_Name_") or not filename.endswith(".uasset"):
                continue
            stripped = filename.removesuffix(".uasset")
            for guess in (
                "/" + stripped.replace("SWZeroCompany/Content", "Game"),
                "/Game/" + stripped,
            ):
                if package_id(guess) in reader.by_package:
                    yield guess
                    break


specs = kit.create_mod("classes_unlocked", priority=10)
tagged = 0
for path in sorted(set(name_parts())):
    editor = specs.asset(path)
    # Anchor on whatever name tag the part already grants. Parts granting none
    # are the procedural recruit pool, and there is nothing to sit beside.
    anchors = [n for n in editor.names if n.startswith(NAME_PREFIX)]
    if len(anchors) != 1:
        continue
    try:
        for tag in WANTED:
            if tag not in editor.names:
                editor.add_gameplay_tag(anchors[0], tag, expect=1)
    except ValueError:
        # A few parts mention their name tag twice, once as a granted tag and
        # once as a requirement. Guessing which container to grow would be a
        # coin flip, so leave those alone.
        continue
    tagged += 1
specs.asset(ANCHOR_A)

# Adding imports grows the header, so find the map again each time rather than
# holding on to an offset from before it moved. The entry count is what keeps
# the search honest.
picker = kit.create_mod("classes_picker", priority=20)
view_model = picker.asset(VIEW_MODEL)

padawan = TACTICAL + "CPD_TacticalSpec_Padawan"
extended = TACTICAL + "CPD_TacticalSpec_PadawanExtended"
warrior = TACTICAL + "CPD_TacticalSpec_Warrior"

pad_key = view_model.add_import(padawan, kit.public_export_hash(padawan))
pad_value = view_model.add_import(extended, kit.public_export_hash(extended))
war_key = view_model.add_import(warrior, kit.public_export_hash(warrior))

view_model.find_object_map(entries=8, referencing="CPD_TacticalSpec_Scout").append(
    pad_key, pad_value
)
view_model.find_object_map(entries=9, referencing="CPD_TacticalSpec_Padawan").append(
    war_key, None
)
picker.asset(ANCHOR_B)

print(f"name parts tagged: {tagged}")
for mod in (specs, picker):
    for path in mod.install():
        print(path.name)
    print(f"  {mod.name}: {mod.changes} edits")
