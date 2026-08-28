"""Let any character take the Jedi class, not just Tel-Rea Vokoss.

    python examples/jedi_for_everyone.py

The Padawan and Wayseeker specialisations put two tags in AllowedSlots. One
is the slot they go in, the other says the character has to carry the name part
"Tel-ReaVokoss". Ordinary classes like Soldier only list the slot.

Those tags sit in the package name map and get referenced by index. Shortening
the list would resize the asset, so instead each gate tag is pointed at the
slot tag next to it. The list ends up as harmless duplicates, the same shape
every other class has, and nothing needs to move.
"""

import zcmodkit

SPECS = "/Game/Game/Customizations/Characters/Common/Specialization/Tactical/"
GATE = "br.Customization.Part.Character.Info.Name.Tel-ReaVokoss"
PRIMARY = "br.Customization.Slot.Character.Specializations.Tactical.Primary"
SECONDARY = "br.Customization.Slot.Character.Specializations.Tactical.Secondary"

# Every gated specialisation, and the slot tag to fall back on.
GATED = [
    ("CPD_TacticalSpec_Padawan", PRIMARY),
    ("CPD_TacticalSpec_PadawanExtended", SECONDARY),
    ("CPD_TacticalSpec_Padawan_SlugHQ", PRIMARY),
    ("CPD_TacticalSpec_PadawanExtended_SlugHQ", SECONDARY),
]

mod = zcmodkit.open().create_mod("jedi_for_everyone", priority=0)

for name, slot_tag in GATED:
    mod.asset(SPECS + name).retarget_name(GATE, slot_tag, expect=1)

mod.install()
