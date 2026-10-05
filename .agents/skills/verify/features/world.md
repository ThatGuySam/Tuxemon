# World and Quest Progression

Players walk through four authored areas and complete connected NPC duties with item and quest guards.

## Sub-features

- Single-step and held movement, companion collision, and interaction hints.
- Four-area traversal, five NPCs, exact-quantity trade, rescue, permit, and epilogue.
- Rejected prerequisites and retained drafts after refusal; journal/reset rendering is covered by the screen gate.

## How to get to it (user POV)

Use directions to walk and A near an NPC to talk. Complete Earth tactics, one-crystal supply trade, name correction, safe route, scout rescue, permit, and return to the Professor. Start opens Journal or Reset. Meaning confirmation applies guarded effects.

## Driving it with PyBoy

Preconditions: fresh bundle with authored initial aid kit and crystal.

- Run `.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature world`.
- Require actual walking and typed messages, the full guarded quest route, inventory consumption, and the final epilogue flag. Fixture mailbox responses must remain labeled protocol tests.
- Read the movement trace for every sampled frame, companion collision positions, sprite positions, and padded interaction hints.
- Run the mapped screen gate for Journal and Reset; the world route alone does not enter those screens.
- Actual NOI/MAP allocations must keep all game data separate from C800 through CBFF.

## Gotchas

This is authored game fiction, not canonical Tuxemon endgame. The full quest route does not claim exhaustive coverage of all 30 authored outcomes. Dedicated attempted-entry tests for walls, water, and NPC footprints are not part of this world gate; route planning avoids those obstacles. Progress is session RAM; reset and quitting clear it. No save is written during verification.
