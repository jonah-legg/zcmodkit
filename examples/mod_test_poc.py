"""Change a main menu button."""

import zcmodkit

kit = zcmodkit.open()
mod = kit.create_mod("mod_test_poc", 100)
mod.asset("/Game/Game/UI/Localization/UI_System_Strings").replace_text(
    "NEW CAMPAIGN", "NEW MODDED CAMPAIGN"
)
mod.install()
