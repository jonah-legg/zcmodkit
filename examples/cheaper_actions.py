"""Make actions cost less.

    python examples/cheaper_actions.py

Every ability cost in the game is a row in one table, so this is about the most
you can change from one place. Undo it with mod.uninstall().
"""

import zcmodkit

COSTS = "/Game/Game/GameData/DynamicGACosts/DT_CostsTable_v4"

mod = zcmodkit.open().create_mod("cheaper_actions")
costs = mod.table(COSTS)

# One field on one row at a time.
costs.set("BitReactor.AbilityCost.BasicAttack", "ActionPointCost", 0.0)
costs.set("BitReactor.AbilityCost.MovementCost", "ActionPointCost", 0.0)
costs.set("BitReactor.AbilityCost.DoubleMovement", "ActionPointCost", 1.0)
costs.set("BitReactor.AbilityCost.TripleMovement", "ActionPointCost", 1.0)

# Or the same field on every row that has one.
costs.set_all("AdvantageCost", 0.0)

mod.install()
