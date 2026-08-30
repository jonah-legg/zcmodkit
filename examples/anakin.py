"""Make Hawks Anakin: his look, his class, his lightsaber and his abilities.

    python examples/anakin.py

Standalone, and one container. Nothing else has to be installed.

There are two problems here and they are not the same problem. Wearing
something and being offered something go through different machinery, so this
does both.


WEARING IT

Anakin's parts are locked to him by name, and his arms, boots and legs ask for
Accepts.AuthoredOnly on top, which nothing in the game grants. But AuthoredOnly
does not mean unreachable, it means only an authored definition may assign me,
and Hawks' presets are authored definitions, the same kind of asset as
CD_Char_Anakin_New. So his kit is assigned rather than unlocked: head, skin
tone, height, and the whole robe including the pieces no tag can reach. Hair,
eyebrow and facial hair are emptied, because SK_HTAM_SkyGuy_Head already
carries all of that.

Every edit in this half repoints a soft object reference - two FNames written
where they stand - which is the one shape this game has never rejected.


BEING OFFERED IT

CustomizationPartDefinition is a scanned Primary Asset Type, so the customizer
does not look at packages. It asks UAssetManager for the parts it knows about,
and that list, along with each part's AllowedSlots, comes from
AssetRegistry.bin. Editing AllowedSlots on the asset therefore does nothing,
and a package the registry has never heard of is invisible however it is
gated. The registry is a plain file inside pakchunk0-Windows.pak, and plain
files cannot be delivered: only IoStore containers mount from ~mods, and
containers hold packages. Proven by shipping a patched Game.locres in a
container-less pak and watching the main menu not change.

So the registry decides which parts exist and what slot each one fits, and it
cannot be touched. What it does not decide is what those parts *are*. Display
name, icon and every fragment come from the package, and packages are exactly
what a container can ship. So: take a part the registry already lists in the
right slot, and edit it into the Jedi Knight.

CPD_TacticalSpec_Anakin cannot be that part - it names no slot at all, so
listing it lists it in every slot, an empty "Jedi Knight" in the torso, arms
and boots lists, and picking one takes the limb away. Tel Rea's name is the
tightest gate that reaches a properly slotted spec: two extra classes and 22
parts, against Accepts.AuthoredOnly's four classes and 1218. Of the two it
reaches, CPD_TacticalSpec_Padawan_SlugHQ is used by a single story-stage
definition rather than by her everyday one, so it is the one that gets edited.

It gets Anakin's name key, his description, the Jedi class icon and his five
abilities. The abilities could not go through the spec's Fragments array -
importing another package's sub-objects stops the container loading - but the
abilities inside its own fragments are soft references, so they are repointed
one at a time, in place.

Two more things had to be true before any of it is offered. The customizer asks
BP_SpecializationSelectionVM, twice, whether a character carries any tag under
br.Customization.Part.Character.Info.Name; Hawks carries his own name, so the
game reads him as an authored hero and hands him a cut-down list of about seven
torsos. Both queries are pointed at a name tag nothing grants. And the grant
that opens Tel Rea's parts has to ride on something that actually overrides:
CPD_H_Name_Hawks looks like the obvious home and never works, the container
loads, the edits beside it land, and the tag simply never arrives.
CPD_TalentSpec_TheLeader does work, Hawks' definition assigns it, and it is
gated on his own name, so whatever it grants stays his alone.


WHAT IT DOES NOT DO

The class is called Jedi Knight and cannot be called anything else. Nothing in
the game's localisation contains the word "Chosen" to point at, editing
Design_Classes_Strings itself stops the container loading, and Game.locres,
which carries the text the game actually displays, is a loose file that cannot
be shipped at all.

Worth knowing before running it: a character's customization is written into
the save when they join, and Hawks joins when the campaign starts. This wants a
new campaign.
"""

import struct

import zcmodkit
from zcmodkit.formats.iostore import package_id

# ---------------------------------------------------------------------------
# What Hawks wears
# ---------------------------------------------------------------------------

#: Slot tags all start with this, which is how an override is picked out of the
#: export data without having to walk every property in front of it.
SLOT = "br.Customization.Slot.Character."

#: What Hawks is given, slot by slot. Straight out of CD_Char_Anakin_New, which
#: is the only place the whole outfit is written down as one character.
ASSIGN = {
    SLOT + "Appearance.Humanoid.Body.Height": "CPD_H_Height_Anakin",
    SLOT + "Appearance.Humanoid.Head.Face.Mesh": "CPD_H_Head_Anakin_New",
    SLOT + "Appearance.Humanoid.Head.Face.SkinTone": "CPD_H_SkinTone_Human_Anakin",
    SLOT + "Outfit.Torso.Mesh": "CPD_H_Outfit_Anakin_TORS",
    SLOT + "Outfit.Arms.Mesh": "CPD_H_Outfit_Anakin_ARMS",
    SLOT + "Outfit.Legs.Mesh": "CPD_H_Outfit_Anakin_LEGS",
    SLOT + "Outfit.Boots.Mesh": "CPD_H_Outfit_Anakin_BOOT",
    # Hawks wears CPD_Char_Class_Hero_Humanoid, whose
    # CustomizationFragmentCharacterClass is empty, so he has no CharacterClass
    # asset and therefore no EquipableItemLimits saying a melee weapon is
    # something he may hold. Anakin's names Class_Hero_Jedi_Anakin, which is
    # also where the Jedi class tag the Force items look for comes from. It
    # brings Anakin's attribute sets with it, so this moves his stats too.
    SLOT + "Class": "CPD_Char_Class_Hero_Jedi_Anakin",
    # The host, not CPD_TacticalSpec_Anakin. An equipped part the picker does
    # not list draws as "None", so it has to be one the picker lists.
    SLOT + "Specializations.Tactical.Primary": "CPD_TacticalSpec_Padawan_SlugHQ",
    SLOT + "Specializations.Weapon": "CPD_WeaponSpec_Melee_1H_Anakin",
    SLOT + "Specializations.Weapon.GearKit": "CPD_GK_Lightsaber_Anakin",
}

#: Slots emptied rather than filled. Anakin's own definition has no hair,
#: eyebrow or facial hair slot at all: SK_HTAM_SkyGuy_Head carries all of it,
#: so anything in those slots sits on top of hair that is already there.
#: An empty override is the name None on both halves of the reference, which is
#: how the game writes the helmet slot Hawks starts with.
EMPTY = (
    SLOT + "Hair.Hair.Mesh",
    SLOT + "Hair.Facial.Mesh",
    SLOT + "Appearance.Humanoid.Head.Eyebrow.Mesh",
)

#: Left alone on purpose: his voiceover says his name out loud.
LEFT_ALONE = ("CPD_H_Voiceover_Anakin",)


# ---------------------------------------------------------------------------
# What Hawks may pick
# ---------------------------------------------------------------------------

#: The carrier for the name grants. Hawks' definition assigns it, and it is
#: gated on his name, so nobody else can take it and nothing it grants leaves
#: him.
TALENT = (
    "/Game/Game/Customizations/Characters/Common/Specialization/Talent/"
    "CPD_TalentSpec_TheLeader"
)
LEADER_TAG = "br.Customization.Part.Character.Specializations.Identity.Leader"

#: What Anakin's own parts ask for, and what the host asks for.
ANAKIN_TAG = "br.Customization.Part.Character.Info.Name.Anakin"
TEL_REA_TAG = "br.Customization.Part.Character.Info.Name.Tel-ReaVokoss"

#: The entry that becomes the Jedi Knight, edited in place. Not copied: a
#: container may only edit packages the game already ships, and substituting
#: one package's contents for another's kills the whole container.
HOST = (
    "/Game/Game/Customizations/Characters/Common/Specialization/Tactical/"
    "CPD_TacticalSpec_Padawan_SlugHQ"
)

#: Which string-table keys the host quotes, and what to quote instead. Both
#: specs draw their name from the same string table, so this is only a matter
#: of which key. It has three: a name, a short description and a long one.
#: Anakin has no long description of his own, so both descriptions take the one
#: he does have, rather than leaving the Padawan blurb behind.
DESCRIPTIONS = {
    "Class_Padawan_Name": "Class_Anakin_Name",
    "Class_Padawan_Description": "Class_Anakin_Description",
    "Class_Padawan_Long": "Class_Anakin_Description",
}

#: The icon is a soft texture reference, repointed the way a slot override is:
#: two names written where they stand.
PADAWAN_ICON = "/Game/Game/UI/Icons/TalentAbilities/T_UI_Passives_Padawan"
JEDI_ICON = "/Game/Game/UI/Icons/Class/T_UI_ClassIcon_Jedi"

#: What the host actually does, ability by ability. It works out at exactly
#: five for five: Anakin has no skill tree at all, his five are all granted
#: outright; the host has three tracks and two granted. The pairing follows the
#: shape of each slot - the host's Ultimate track takes his Ultimate Lightsaber
#: Throw, its Force Push track takes his Force Push, its passive training track
#: takes his Meditation.
ABILITIES = {
    "GA_Shockwave_T2": "GA_LightsaberThrow_Anakin",
    "GA_ForcePush_T2": "GA_ForcePush_Anakin",
    "GA_PadawanTraining_T2": "GA_AnakinMeditation_T1",
    "GA_NobleDefense_Initialize": "GA_NobleStance_Anakin",
    "GA_CanOneShot": "GA_AnakinDefense_T1",
}

#: The lock, and what its two queries get pointed at instead. It has to be a
#: name tag so they keep their shape, and one no part grants, so neither ever
#: matches again. A retarget, so nothing is resized and no export moves.
VIEW_MODEL = (
    "/Game/Game/UI/Strategy/Personnel/FocusTree/BP/BP_SpecializationSelectionVM"
)
LOCK_TAG = "br.Customization.Part.Character.Info.Name"
NOBODY = "br.Customization.Part.Character.Info.Name.Nobody"

#: Every container that has loaded in this game holds at least one package with
#: no imports, and one where everything has imports has never loaded. Why is
#: not worked out, so the container carries a spare package to stay on the side
#: that works. It ships unchanged and does nothing else.
#:
#: One container wants exactly one spare, and two mods must never carry the
#: same one: only the lower priority one actually provides it, and the other is
#: left with nothing import-free that loads, and then goes quiet. Which is a
#: good half of why this is a single mod.
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


def slot_overrides(editor):
    """Every slot override in a definition: slot tag, and where its value sits.

    An override is a slot tag as an FName, then the part it points at as a soft
    reference: the package as an FName, the asset as a second FName, and an
    empty sub-path string. Twenty-eight bytes in all. Matching on the whole
    shape rather than on any one field is what keeps this off the runs of
    zeroes that a low name index would otherwise find everywhere.

    The walk goes a byte at a time on purpose. Unversioned property data is not
    padded, so an override can begin at any offset, and stepping four at a time
    finds three quarters of them and quietly loses the rest.
    """
    start, end = editor.package.export_data_range()
    names = editor.names
    slots = {i: n for i, n in enumerate(names) if n.startswith(SLOT)}
    found, at = {}, start
    while at < end - 28:
        index, number = struct.unpack_from("<II", editor.data, at)
        if number == 0 and index in slots:
            package, p_num, asset, a_num, sub = struct.unpack_from(
                "<IIIII", editor.data, at + 8
            )
            if (
                p_num == 0
                and a_num == 0
                and sub == 0
                and package < len(names)
                and asset < len(names)
                and names[package].startswith("/Game/")
                and "/" not in names[asset]
            ):
                found[slots[index]] = at + 8
                at += 28
                continue
        at += 1
    return found


mod = kit.create_mod("anakin", priority=15)


# ---------------------------------------------------------------------------
# Give every Hawks preset Anakin's kit
# ---------------------------------------------------------------------------

presets = sorted(
    {
        name
        for reader in kit.containers
        for filename in reader.files
        if "/CD_Char_Hero_Hawks_" in filename and filename.endswith(".uasset")
        # The ones character creation offers end in the body type, or are the
        # default. CD_Char_Hero_Hawks_BespinGuard_Outfit is a disguise worn for
        # one mission, and dressing that as a Jedi rather defeats it.
        if (name := filename.rsplit("/", 1)[-1].removesuffix(".uasset")).endswith(
            ("_M", "_F", "_Default")
        )
    }
)

#: Resolved once. find_package walks every file in every container, and there
#: are eighteen presets to do this for.
targets = {slot: (find_package(part), part) for slot, part in ASSIGN.items()}

for preset in presets:
    definition = mod.asset(find_package(preset))

    # Names first, all of them: each one moves the export data along, and the
    # offsets below have to be worked out once everything has settled.
    added = {
        slot: (definition.add_name(path), definition.add_name(obj))
        for slot, (path, obj) in targets.items()
    }
    nobody = definition.add_name("None")

    places = slot_overrides(definition)
    for slot, (package, asset) in added.items():
        at = places.get(slot)
        if at is None:
            continue  # a preset that does not define this slot, or leaves it empty
        struct.pack_into("<IIII", definition.data, at, package, 0, asset, 0)
        definition.changes += 1

    for slot in EMPTY:
        at = places.get(slot)
        if at is None:
            continue  # species with no hair slot to empty in the first place
        struct.pack_into("<IIII", definition.data, at, nobody, 0, nobody, 0)
        definition.changes += 1


# ---------------------------------------------------------------------------
# Open the lists his own name closes
# ---------------------------------------------------------------------------

talent = mod.asset(TALENT)
talent.add_gameplay_tag(LEADER_TAG, ANAKIN_TAG, expect=1)
talent.add_gameplay_tag(LEADER_TAG, TEL_REA_TAG, expect=1)

view_model = mod.asset(VIEW_MODEL)
view_model.add_name(NOBODY)
view_model.retarget_name(LOCK_TAG, NOBODY, expect=2)


# ---------------------------------------------------------------------------
# Make the host read, and play, as the Jedi Knight
# ---------------------------------------------------------------------------

host = mod.asset(HOST)
for padawan_key, anakin_key in DESCRIPTIONS.items():
    host.replace_text(padawan_key, anakin_key)

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


mod.asset(ANCHOR)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

for path in mod.install():
    print(path.name)
print(f"  {mod.name}: {mod.changes} edits")
