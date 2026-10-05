# Screen Rendering

Players should navigate screens without the visible content being cleared before it is repainted.

## Sub-features

- Menu cursor, scrolling, wraparound, journal, and reset.
- All ROM phases, including host waiting and cancellation.
- Every editor, preview, meaning picker, reply pagination, and world return.
- Historical blinking-build rejection with retained failure evidence.

## How to get to it (user POV)

Press Start in the world or an editor. Up/Down changes menu selection. A chooses; B or Start resumes. Talk to the Professor to reach the editor, preview text, Send, inspect the proposed meaning, and continue the reply. Paired Receive reaches the host-wait screen in the owned Mac bridge. Journal and Reset are menu entries.

## Driving it with PyBoy

Preconditions: fresh `launch` bundle and passing `doctor`.

- Run `.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature screens`.
- Require the coverage manifest to include every enumerated phase and method. Every driven frame must keep LCD enabled and visible content; stable navigation regions must retain their actual pixels.
- Inspect action/state records and intermediate PNGs, not only final screenshots. A missing path is a failure, not an inferred pass.
- Run `.agents/skills/verify/scripts/control.py negative-control --run "$VERIFY_RUN"`. The preserved old ROM must fail specifically for blanking or heading erasure.

## Gotchas

Boot frames are allowed to initialize before the visible-game checks begin. Intentional text deletion should clear obsolete characters; it must preserve unrelated content. Scene transitions are not a hardware-atomic background swap. The negative-control success means the old build was rejected, not that it passed rendering verification.
