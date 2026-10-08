# Earlier Movement Redraw Fix

The latest shared menu/editor correction is recorded in [Shared Screen Redraw Fix](../screens/RESULTS.md). The records below describe the earlier movement-only build, preserved at `build/chromatic/playground-before-ui-fix/playground.gbc`.

The supplied screen recording showed the world disappear and redraw on every step. The same ROM reproduced this through actual PyBoy button input. The previous movement renderer cleared all background rows, hid sprites, and then repainted the entire scene. One sampled frame had zero dark pixels, showing a fully blank display.

Ordinary movement within an unchanged world now moves the player sprite through OAM. The renderer updates the padded interaction hint only when NPC proximity changes. Area, screen, quest, and inventory changes retain the full rendering path.

The corrected ROM SHA-256 is `b9b54bf6d16cfbaf562b8ed1d0f65a085d7e22e7788697c844d0d6005df6bc93`. The unchanged canonical world and live bridge use the same source-pinned model pipeline as before.

## Verified Results

All 104 sampled frames passed across single-step movement, blocked companion collision, held-direction repeat, and the NPC interaction-hint boundary. Every frame retained the same world tilemap, enabled LCD and sprites, and nonwhite pixels. Tests checked exact hint padding and actual hardware sprite positions. Full editor, quest, timeout, and 22 invalid-builder/layout checks passed. Scoped Ruff passed. Independent review accepted the source and compiled fix.

Before and after traces and actual frames are stored beside this record. Physical display and controls are not claimed from the emulator checks. No cartridge or firmware was written.

Prove It Works shaped the frame-by-frame ROM check. Fix Root Causes shaped removal of the background clear during movement, rather than a delay or display toggle.

The persistent real integration verifier also passed all four cases on the corrected ROM: GLiClass, paired HTTP input, Ollama draft composition, and authored fallback. Its actual receipt is `real-model-rom-e2e.json`. The fresh Mac game is running with paired input at `http://127.0.0.1:59096/`; the prior game session remains open.
