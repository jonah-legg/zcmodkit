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
name tags those parts ask for does work, and the tidiest place to do that is
the Zero Company faction part. Everyone in the squad wears it, authored
characters and recruits alike, so one edit covers the lot.

Mandalorian armour is a separate problem with the same shape. The pieces ask
for Accepts.Outfit.Mdo, and of the three class parts that grant it none is the
one player characters wear, so the armour is only ever reachable through Cly's
presets. Granting that tag puts every piece in the list as its own choice. The
helmets get a human requirement added on the way past, since they are modelled
for human heads and sit badly on anything with horns or lekku.

There is a third piece to it. BP_SpecializationSelectionVM holds a map of
primary specialisation to secondary, and a class the map does not mention has
nothing to pair with. Padawan gets an entry pointing at Wayseeker, Warrior gets
one pointing at nothing, which is what Cly's own definition does.

And a fourth, which the name tags bring on themselves. The same view model
decides a character's specialisation and talent cannot be changed at all when
they carry any tag under br.Customization.Part.Character.Info.Name, which in
the unmodified game only authored heroes do. That is how Tel Rea stays a
Padawan and Cly stays a Warrior. Handing those tags to the whole squad reads
every character as an authored hero, so the class you assign first is the one
they keep. Both queries get pointed at a tag nothing grants instead.

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
FACTION = (
    "/Game/Game/Customizations/Characters/Common/Info/Faction/CPD_Faction_ZeroCompany"
)
VIEW_MODEL = (
    "/Game/Game/UI/Strategy/Personnel/FocusTree/BP/BP_SpecializationSelectionVM"
)

PADAWAN = TACTICAL + "CPD_TacticalSpec_Padawan"
WAYSEEKER = TACTICAL + "CPD_TacticalSpec_PadawanExtended"
WARRIOR = TACTICAL + "CPD_TacticalSpec_Warrior"

#: The tags the locked classes ask for. Give these to a character and the
#: classes their owners hold become available to them. Padawan and Wayseeker
#: want the first, Warrior the second, and both also ask for the ordinary
#: tactical slot tag that every character already carries.
WANTED_TAGS = (
    "br.Customization.Part.Character.Info.Name.Tel-ReaVokoss",
    "br.Customization.Part.Character.Info.Name.ClyKullervo",
)

#: The tag the faction part already grants. Containers are not labelled in
#: cooked data, so this is how the right one gets picked out.
FACTION_TAG = "br.Customization.Part.Character.Info.Faction.ZeroCompany"

#: What the view model reads as "this character is an authored hero, their
#: specialisation and talent are not theirs to change". It is the parent of
#: every name tag, so either of the two handed out above trips it.
LOCK_TAG = "br.Customization.Part.Character.Info.Name"

#: What the two locking queries get pointed at instead. It has to be a name tag
#: so the queries keep the shape they had, and it has to be one no part grants,
#: so nothing ever matches. No character is called this.
NOBODY = "br.Customization.Part.Character.Info.Name.Nobody"

#: What the Mandalorian outfit pieces ask for. Only three class parts grant it
#: and none of them is the one player characters wear.
MDO = "br.Customization.Accepts.Outfit.Mdo"

#: Humans get this from their species part, nobody else does. Adding it to the
#: Mando helmets keeps them off heads they were never modelled for.
HUMAN_HELM = "br.Customization.Accepts.Helm.Human"

#: The helmets, by package name. The rest of the armour is left open to
#: everyone.
MANDO_HELMETS = (
    "CPD_H_Outfit_Man001A_HELM",
    "CPD_H_Outfit_Man002A_HELM",
    "CPD_H_Outfit_Cly_HELM",
    "CPD_H_Outfit_ClyB_HELM",
)

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

# Tagging each character's own name part would work too, but most of the
# recruit pool inherits from a base that grants no name tag, so there would be
# nothing to hang these off and new recruits would miss out. The faction part
# has no such gap.
specs = kit.create_mod("classes_unlocked", priority=10)
faction = specs.asset(FACTION)
for tag in (*WANTED_TAGS, MDO):
    faction.add_gameplay_tag(FACTION_TAG, tag, expect=1)


# ---------------------------------------------------------------------------
# Keep the Mando helmets on human heads
# ---------------------------------------------------------------------------


def find_package(basename):
    """Look a package up by its file name, whichever container holds it."""
    for reader in kit.containers:
        for filename in reader.files:
            if not filename.endswith("/" + basename + ".uasset"):
                continue
            stripped = filename.removesuffix(".uasset")
            for guess in (
                "/" + stripped.replace("SWZeroCompany/Content", "Game"),
                "/Game/" + stripped,
            ):
                if package_id(guess) in reader.by_package:
                    return guess
    raise KeyError(basename)


for helmet in MANDO_HELMETS:
    # Sits next to the tag the piece already asks for, so it becomes one more
    # requirement rather than a new container.
    specs.asset(find_package(helmet)).add_gameplay_tag(MDO, HUMAN_HELM, expect=1)

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


# ---------------------------------------------------------------------------
# Half three: stop the picker treating the whole squad as authored heroes
# ---------------------------------------------------------------------------

# SpecLockedQuery and TalentLockedQuery both ask the same thing: does this
# character carry any tag under LOCK_TAG. Half one gives all of them two, so
# left alone every character's class and talent would come out locked the
# moment they had one, and the first class assigned would be the last. The tag
# sits in the name map with the export data pointing at it by index, so both
# queries can be sent somewhere harmless without moving a byte. One reference
# each is the whole of it.
view_model.add_name(NOBODY)
view_model.retarget_name(LOCK_TAG, NOBODY, expect=2)

picker.asset(ANCHOR_B)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

for mod in (specs, picker):
    for path in mod.install():
        print(path.name)
    print(f"  {mod.name}: {mod.changes} edits")
