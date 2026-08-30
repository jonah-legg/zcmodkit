"""Let Hawks pick Anakin's kit, rather than only wear it.

    python examples/anakin_unlock.py

The companion to anakin_look.py, which assigns the look. This is the half that
makes things selectable, and every line of it was found by bisecting, so the
reasons are worth keeping.

Two things have to be true before the customizer offers Hawks anything.

BP_SpecializationSelectionVM asks, twice, whether a character carries any tag
under br.Customization.Part.Character.Info.Name. Hawks carries his own name, so
the game reads him as an authored hero and hands him a cut-down list: about
seven torsos and nothing else. Pointing both queries at a name tag nothing
grants lifts that.

And the grant has to ride on a part that actually overrides. CPD_H_Name_Hawks
looks like the obvious home and never works: the container loads, the edits
beside it land, and the tag simply never arrives. CPD_TalentSpec_TheLeader does
work, Hawks' definition assigns it, and it is gated on his own name, so
whatever it grants stays his alone.

Then the class. CPD_TacticalSpec_Anakin names no slot in its AllowedSlots, so
listing it lists it in every slot: an empty "Jedi Knight" in the torso, arms
and boots lists, and picking one takes the limb away. AllowedSlots lives in
AssetRegistry.bin and no mod can write it, so his own spec can never be
offered properly. What can is a part that is already listed and does name the
slot, edited to read as his.

Tel Rea's name is the tightest gate that reaches one: two extra classes and 22
parts, against Accepts.AuthoredOnly's four classes and 1218 parts. Of the two
it reaches, CPD_TacticalSpec_Padawan_SlugHQ is used by a single story-stage
definition rather than by her everyday one.

The one thing this does not do is give it Anakin's abilities. Those live in the
spec's Fragments array, and pointing that at his fragments, imported from his
package, stops the container loading. So the entry reads as the Jedi Knight and
plays as a Padawan, which is at least the game's own Jedi tree.
"""

import struct

import zcmodkit
from zcmodkit.formats.iostore import package_id

#: The carrier. Hawks' definition assigns it, and it is gated on his name, so
#: nobody else can take it and nothing it grants leaves him.
TALENT = (
    "/Game/Game/Customizations/Characters/Common/Specialization/Talent/"
    "CPD_TalentSpec_TheLeader"
)
LEADER_TAG = "br.Customization.Part.Character.Specializations.Identity.Leader"

#: What his parts ask for, and what the host asks for.
ANAKIN_TAG = "br.Customization.Part.Character.Info.Name.Anakin"
TEL_REA_TAG = "br.Customization.Part.Character.Info.Name.Tel-ReaVokoss"

#: The entry that becomes the Jedi Knight, edited in place. Not copied: a
#: container may only edit packages the game already ships, and substituting
#: one package's contents for another's kills the whole container.
#:
#: Both specs draw their name from the same string table, so this is a matter
#: of which key is quoted. The icon is a soft texture reference, repointed the
#: way a slot override is: two names written where they stand.
HOST = (
    "/Game/Game/Customizations/Characters/Common/Specialization/Tactical/"
    "CPD_TacticalSpec_Padawan_SlugHQ"
)
PADAWAN_KEY = "Class_Padawan_Name"
ANAKIN_KEY = "Class_Anakin_Name"
PADAWAN_ICON = "/Game/Game/UI/Icons/TalentAbilities/T_UI_Passives_Padawan"
JEDI_ICON = "/Game/Game/UI/Icons/Class/T_UI_ClassIcon_Jedi"

#: What the host actually does, ability by ability.
#:
#: Its Fragments array cannot be pointed at Anakin's fragments - importing
#: another package's sub-objects stops the container loading. But the
#: abilities inside its own fragments are soft references, package and asset as
#: two FNames, which is the one shape that has never failed here. So they are
#: repointed one at a time, in place.
#:
#: It works out at exactly five for five. Anakin has no skill tree at all, his
#: five are all granted outright; the host has three tracks and two granted.
#: The pairing follows the shape of each slot: the host's Ultimate track takes
#: his Ultimate Lightsaber Throw, its Force Push track takes his Force Push,
#: its passive training track takes his Meditation.
ABILITIES = {
    "GA_Shockwave_T2": "GA_LightsaberThrow_Anakin",
    "GA_ForcePush_T2": "GA_ForcePush_Anakin",
    "GA_PadawanTraining_T2": "GA_AnakinMeditation_T1",
    "GA_NobleDefense_Initialize": "GA_NobleStance_Anakin",
    "GA_CanOneShot": "GA_AnakinDefense_T1",
}

#: The lock, and what its two queries get pointed at instead. It has to be a
#: name tag so they keep their shape, and one no part grants, so neither ever
#: matches again.
VIEW_MODEL = (
    "/Game/Game/UI/Strategy/Personnel/FocusTree/BP/BP_SpecializationSelectionVM"
)
LOCK_TAG = "br.Customization.Part.Character.Info.Name"
NOBODY = "br.Customization.Part.Character.Info.Name.Nobody"

#: Every container that has loaded in this game holds at least one package with
#: no imports. DT_CostsTable_v4 is the only one with evidence behind it, so
#: both containers carry it and the conflict that reports is harmless: they are
#: identical untouched copies.
ANCHOR = "/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4"


kit = zcmodkit.open()


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


mod = kit.create_mod("anakin_unlock", priority=16)


# ---------------------------------------------------------------------------
# The grants
# ---------------------------------------------------------------------------

talent = mod.asset(TALENT)
talent.add_gameplay_tag(LEADER_TAG, ANAKIN_TAG, expect=1)
talent.add_gameplay_tag(LEADER_TAG, TEL_REA_TAG, expect=1)


# ---------------------------------------------------------------------------
# Make the host read as the Jedi Knight
# ---------------------------------------------------------------------------

host = mod.asset(HOST)
host.replace_text(PADAWAN_KEY, ANAKIN_KEY)

icon_package = host.add_name(JEDI_ICON)
icon_asset = host.add_name(JEDI_ICON.rsplit("/", 1)[-1])
was = struct.pack(
    "<IIII",
    host.names.index(PADAWAN_ICON),
    0,
    host.names.index(PADAWAN_ICON.rsplit("/", 1)[-1]),
    0,
)
now = struct.pack("<IIII", icon_package, 0, icon_asset, 0)
start, end = host.package.export_data_range()
found, at = 0, start
while (i := host.data.find(was, at, end)) >= 0:
    host.data[i : i + len(now)] = now  # SmallImage and LargeImage both
    found += 1
    at = i + 1
if not found:
    raise ValueError("could not find the icon reference to repoint")
host.changes += 1


# Give it his abilities. Names first, all of them: each one moves the export
# data along, and the references have to be found after everything settles.
swaps = []
for old_ability, new_ability in ABILITIES.items():
    old_package = next(n for n in host.names if n.endswith("/" + old_ability))
    swaps.append(
        (
            struct.pack(
                "<IIII",
                host.names.index(old_package),
                0,
                host.names.index(old_ability + "_C"),
                0,
            ),
            struct.pack(
                "<IIII",
                host.add_name(find_package(new_ability)),
                0,
                host.add_name(new_ability + "_C"),
                0,
            ),
        )
    )

start, end = host.package.export_data_range()
for before, after in swaps:
    where = host.data.find(before, start, end)
    if where < 0:
        raise ValueError("an ability reference went missing before it was written")
    host.data[where : where + len(after)] = after
    host.changes += 1


# ---------------------------------------------------------------------------
# Stop the game treating Hawks as an authored hero
# ---------------------------------------------------------------------------

view_model = mod.asset(VIEW_MODEL)
view_model.add_name(NOBODY)
view_model.retarget_name(LOCK_TAG, NOBODY, expect=2)

mod.asset(ANCHOR)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

for path in mod.install():
    print(path.name)
print(f"  {mod.name}: {mod.changes} edits")
