"""Make Hawks Anakin, and try to make his kit selectable as well.

    python examples/anakin_extras.py

A working copy of anakin_unlocked. It builds the same container under the
same name, so running either one swaps which build is installed and
anakin_unlocked stays the known-good fallback.

Standalone. Nothing else has to be installed for it to work.

There are two halves, and the second one is a trick.

The first half is straightforward. Anakin's parts are locked to him by name,
and his arms, boots and legs ask for Accepts.AuthoredOnly on top, which nothing
in the game grants. But AuthoredOnly does not mean unreachable, it means only
an authored definition may assign me, and Hawks' presets are authored
definitions, the same kind of asset as CD_Char_Anakin_New. So his kit is
assigned rather than unlocked: head, skin tone, height, and the whole robe
including the pieces no tag can reach. His hair, eyebrow and facial hair slots
are emptied, because SK_HTAM_SkyGuy_Head already carries all of that.

The second half is about being *offered* something rather than wearing it, and
that turns out to be a different problem entirely.

CustomizationPartDefinition is a scanned Primary Asset Type, so the customizer
does not look at packages. It asks UAssetManager for the parts it knows about,
and that list, along with each part's AllowedSlots, comes from
AssetRegistry.bin. Editing AllowedSlots on the asset therefore does nothing,
and a package the registry has never heard of is invisible however it is
gated. The registry is a plain file inside pakchunk0-Windows.pak, but plain
files cannot be delivered: only IoStore containers mount from ~mods, and
containers hold packages. Proven by shipping a patched Game.locres in a
container-less pak and watching the main menu not change.

So the registry decides which parts exist and what gates them, and it cannot
be touched. What it does not decide is what those parts *are*. Display name,
icon and every fragment come from the package, and packages are exactly what a
container can ship.

Hence the trick: take a part the registry already lists and hand it Anakin's
contents. CPD_TacticalSpec_Scoundrel is listed, ungated, and paired in the
picker's map. Ship Anakin's tactical spec at Scoundrel's package path, rename
its object to CPD_TacticalSpec_Scoundrel, and the registry finds exactly what
it expects while the player sees a card reading Jedi Knight with the Jedi
class icon and Anakin's ability tracks behind it.

Renaming is only possible because a public export hash turns out to be
CityHash64 of the object name, lowercased, as UTF-16. Checked against the
game's own hashes for both parts before relying on it.

The same trick puts his lightsaber specialisation on CPD_WeaponSpec_Blaster_
Longarm, and that one pays a bonus: taking it grants
Part.Character.Specializations.Weapon.Melee.1H, which is what
CPD_GK_Lightsaber_Anakin asks for, and that gear kit has no name gate. So the
lightsaber itself appears in the gear kit list on its own.

The price is honest and worth stating: the Scoundrel class and the Longarm
weapon class are replaced, not added. There is no way to add a part to the
list, only to change one that is already in it.

His specialisation is not assigned, so the tutorial still hands him a blaster
and can be finished. Pick the Jedi Knight afterwards.

Worth knowing before you run it: a character's customization is written into
the save when they join, and Hawks joins when the campaign starts. This wants a
new campaign.
"""

import struct

import zcmodkit
from zcmodkit.formats.iostore import package_id

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
    SLOT + "Specializations.Tactical.Primary": "CPD_TacticalSpec_Anakin",
    SLOT + "Specializations.Weapon": "CPD_WeaponSpec_Melee_1H_Anakin",
    SLOT + "Specializations.Weapon.GearKit": "CPD_GK_Lightsaber_Anakin",
}

#: Two things have to be true before Hawks can *pick* anything, and both were
#: found the hard way.
#:
#: BP_SpecializationSelectionVM asks, twice, whether a character carries any
#: tag under br.Customization.Part.Character.Info.Name. Hawks carries his own
#: name, so the game reads him as an authored hero and hands him a cut-down
#: list. Pointing both queries at a name tag nothing grants lifts that. It is a
#: retarget, so no container is resized and no export moves.
#:
#: And the grant has to be carried by the right part. CPD_H_Name_Hawks looks
#: like the obvious home for it and does not work: the container loads, the
#: view model edit beside it lands, and the tag simply never arrives.
#: CPD_TalentSpec_TheLeader does work. Hawks' definition assigns it, it is
#: gated on his own name so nobody else can take it, and it already has a
#: GameplayTags container. Still his alone.
TALENT = (
    "/Game/Game/Customizations/Characters/Common/Specialization/Talent/"
    "CPD_TalentSpec_TheLeader"
)
LEADER_TAG = "br.Customization.Part.Character.Specializations.Identity.Leader"
ANAKIN_TAG = "br.Customization.Part.Character.Info.Name.Anakin"

#: Accepts.AuthoredOnly gates about twelve hundred parts and no character
#: carries it. Granting it from a carrier that overrides is what puts the extra
#: tactical specialisations in Hawks' list.
AUTHORED_ONLY = "br.Customization.Accepts.AuthoredOnly"

VIEW_MODEL = (
    "/Game/Game/UI/Strategy/Personnel/FocusTree/BP/BP_SpecializationSelectionVM"
)
LOCK_TAG = "br.Customization.Part.Character.Info.Name"
NOBODY = "br.Customization.Part.Character.Info.Name.Nobody"

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

COMMON = "/Game/Game/Customizations/Characters/Common/Specialization/"

#: Every container that has loaded in this game holds at least one package with
#: no imports, and one where everything has imports has never loaded. Why is
#: not worked out, so each container carries a spare package to stay on the
#: side that works. They ship unchanged and do nothing else.
#:
#: One each, and that matters. When two mods carry the same spare, only the
#: lower priority one actually provides it; the other has its copy shadowed and
#: is left with nothing import-free that loads, and then the whole container
#: goes quiet. classes_unlocked uses two different spares for exactly this
#: reason, and collapsing them to one is what stopped the masquerade loading
#: while its own bytes were perfectly correct.
ANCHORS = (
    "/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4",
    "/Game/Game/FX/Data/STRUCT_FX_DS_Destroy",
    "/Game/Game/GameData/Curves/InteractVisibility",
)


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

mod = kit.create_mod("anakin_hawks", priority=15)
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
# Let him pick them, not only wear them
# ---------------------------------------------------------------------------

# One container, everything in it. Two containers was a guess built on a
# theory about intra-container references that was never actually proven, and
# with the presets in one and these in the other only one of the two ever took
# effect: the look and class went missing while the lists stayed open. Each
# half works alone, so the split was the problem, not either half.
talent = mod.asset(TALENT)
talent.add_gameplay_tag(LEADER_TAG, ANAKIN_TAG, expect=1)
talent.add_gameplay_tag(LEADER_TAG, AUTHORED_ONLY, expect=1)

view_model = mod.asset(VIEW_MODEL)
view_model.add_name(NOBODY)
view_model.retarget_name(LOCK_TAG, NOBODY, expect=2)

mod.asset(ANCHORS[0])


for each in (mod,):
    for path in each.install():
        print(path.name)
    print(f"  {each.name}: {each.changes} edits")
