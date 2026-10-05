# Conversation Drafting

Players can express a message using any of the nine ranked input methods, inspect exact wording, and explicitly choose when to send it.

## Sub-features

- Intent, keywords, initials, grid, groups, direction codes, weighted tree, radial groups, and paired text.
- Literal spelling, all 95 printable ASCII characters, the 96-character limit, and shorter-tail deletion.
- Preview, draft preservation, cancellation, and meaning confirmation before effects.

## How to get to it (user POV)

Talk near an NPC with A and advance its opening to the composer. Start changes the input method while keeping an unsent draft for that NPC. Spell opens the character grid. PREVIEW opens exact text; SEND THIS TEXT submits it. Paired host uses Receive plus authenticated Mac text entry.

## Driving it with PyBoy

Preconditions: fresh bundle and passing doctor; host boundaries in the screen suite are explicitly labeled fixtures.

- Run `.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature screens` for all input-mode rendering and typed/deleted text.
- Run `.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature world` for full draft preservation, limit, explicit commit, cancellation, and guarded effects.
- Require observed draft bytes to equal the literal entered text, stale text cells to become blank, and preview to leave Send count unchanged.
- Use the separately mapped live path to establish real paired/model behavior. Synthetic rendering fixtures cannot replace that proof.

## Gotchas

The ranking is a design judgment. The weighted tree and direction alphabet are custom experiments. Offline paired mode offers spelling but cannot receive phone input. Printable ASCII is an intentional boundary; non-ASCII and overlong paired messages must be rejected rather than silently truncated.
