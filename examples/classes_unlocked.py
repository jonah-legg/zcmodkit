"""Open up the specialisations the game keeps to one character each.

    python examples/classes_unlocked.py

Four classes are locked to their owners:

    Padawan and Wayseeker    Tel-Rea Vokoss
    Warrior and Combat Jump  Cly Kullervo

All four are held back the same way. The part lists a tag in AllowedSlots that
only its owner carries, and a part is offered only when the slot carries every
tag the part asks for.

The fix has to happen on the character side. What the picker offers is read
from the copy of AllowedSlots cached in AssetRegistry.bin rather than from the
asset, so editing the part changes nothing at all. Handing every character the
name tags those parts ask for does work, and that is what this does, adding
them to the name parts beside the character's own.

There is a second half to it. BP_SpecializationSelectionVM holds a map of
primary specialisation to secondary, and a class the map does not mention has
nothing to pair with. Padawan gets an entry pointing at Wayseeker, Warrior gets
one pointing at nothing, which is what Cly's own definition does.

Worth knowing before you run it: a character's customization is written into
the save when they join, so this only reaches characters built afterwards. New
campaigns and new recruits pick it up. The squad you already have will not.
"""

import zcmodkit
from zcmodkit.formats.iostore import package_id

# ---------------------------------------------------------------------------
# What we are changing
# ---------------------------------------------------------------------------

TACTICAL = "/Game/Game/Customizations/Characters/Common/Specialization/Tactical/"
VIEW_MODEL = (
    "/Game/Game/UI/Strategy/Personnel/FocusTree/BP/BP_SpecializationSelectionVM"
)

PADAWAN = TACTICAL + "CPD_TacticalSpec_Padawan"
WAYSEEKER = TACTICAL + "CPD_TacticalSpec_PadawanExtended"
WARRIOR = TACTICAL + "CPD_TacticalSpec_Warrior"

#: The tags the locked classes ask for. Give these to a character and the
#: classes their owners hold become available to them.
WANTED_TAGS = (
    "br.Customization.Part.Character.Info.Name.Tel-ReaVokoss",
    "br.Customization.Part.Character.Info.Name.ClyKullervo",
)

#: Every name tag lives under here, including the one each character already
#: has. That existing tag is what we hang the new ones next to.
NAME_TAG_PREFIX = "br.Customization.Part.Character.Info.Name."

#: Every container that has loaded in this game holds at least one package with
#: no imports, and one where everything has imports has never loaded. Why is
#: not worked out, so each mod carries a spare package to stay on the side that
#: works. These ship unchanged and do nothing else.
ANCHOR_A = "/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4"
ANCHOR_B = "/Game/Game/FX/Data/STRUCT_FX_DS_Destroy"


kit = zcmodkit.open()


# ---------------------------------------------------------------------------
# Half one: hand every character the name tags the locked classes ask for
# ---------------------------------------------------------------------------


def name_parts():
    """Every CPD_H_Name_* package, by its /Game/... path.

    The two containers mount at different points, so the path is worked out by
    trying both shapes and keeping whichever one the container knows about.
    """
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

    # Hang the new tags off whatever name tag the part already grants. Parts
    # granting none are the procedural recruit pool, and there is nothing there
    # to sit beside.
    anchors = [name for name in editor.names if name.startswith(NAME_TAG_PREFIX)]
    if len(anchors) != 1:
        continue

    try:
        for tag in WANTED_TAGS:
            if tag not in editor.names:
                editor.add_gameplay_tag(anchors[0], tag, expect=1)
    except ValueError:
        # A few parts mention their name tag twice, once as a granted tag and
        # once as a requirement. Guessing which container to grow would be a
        # coin flip, so leave those alone.
        continue

    tagged += 1

specs.asset(ANCHOR_A)


# ---------------------------------------------------------------------------
# Half two: give the picker's map an entry for each new class
# ---------------------------------------------------------------------------

picker = kit.create_mod("classes_picker", priority=20)
view_model = picker.asset(VIEW_MODEL)

# The view model has never referenced these three, so each needs an import
# before the map can point at it.
padawan_ref = view_model.add_import(PADAWAN, kit.public_export_hash(PADAWAN))
wayseeker_ref = view_model.add_import(WAYSEEKER, kit.public_export_hash(WAYSEEKER))
warrior_ref = view_model.add_import(WARRIOR, kit.public_export_hash(WARRIOR))

# Adding those imports grew the header, so look the map up again each time
# rather than holding on to an offset from before it moved. Asking for a
# specific entry count is what keeps the search honest.
view_model.find_object_map(entries=8, referencing="CPD_TacticalSpec_Scout").append(
    padawan_ref, wayseeker_ref
)
view_model.find_object_map(entries=9, referencing="CPD_TacticalSpec_Padawan").append(
    warrior_ref,
    None,  # Warrior has no secondary
)

picker.asset(ANCHOR_B)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

print(f"name parts tagged: {tagged}")
for mod in (specs, picker):
    for path in mod.install():
        print(path.name)
    print(f"  {mod.name}: {mod.changes} edits")
