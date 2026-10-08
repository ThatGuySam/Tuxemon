# Shared Screen Redraw Fix

The previous movement correction did not cover the shared renderer used by menus, editors, and dialogue. Root reproduced menu Down on the previous ROM: its heading disappeared in frames three through seven, and frame seven was entirely blank.

Every screen now builds a 20 by 18 tile canvas in WRAM. The renderer compares it with a retained visible map and commits only changed tile runs. Clearing the desired canvas never clears the display first. Font tile IDs are learned through the public GBDK character renderer at startup while the LCD is off. World movement retains its sprite-only path.

## Verified Results

The corrected ROM is 32,768 bytes, SHA-256 `ef806f6a27c18cdf9da86562c6691612307691681f7a1d9ecb24953955b4282e`. Root rebuilt it and reran all screen, movement, native gameplay, and memory-layout checks. Independent review accepted the frozen source.

All 76 named screen traces, totaling 1,520 recorded LCD frames, retained visible content. Menu cursor movement and scrolling preserved headings. Checks covered all eight local editors, shorter draft deletion, all 95 printable glyphs, preview, meaning selection, reply pages, world transitions, and sprite visibility. The 104-frame movement regression, full quest/editor/timeout verifier, 22 invalid-content/layout checks, and scoped Ruff also passed.

The retained renderer can update large scene changes over several frames. It preserves visible content during those changes. This is not an atomic hardware background-map swap, and these emulator checks do not establish physical display behavior.

The two 360-byte canvases, 95-byte font map, and game data fit before the fixed C800 mailbox. Linker-verified data ends at C4F6. No dependencies, classifier policy, content, cartridge, or firmware were changed.

Prove It Works shaped checks of every intermediate LCD frame. Fix Root Causes shaped correction of the shared clear-before-paint path rather than another menu-only workaround.

The persistent live integration checks also passed on this ROM. Their receipt is `real-model-rom-e2e.json`. A fresh Mac game is running with paired input at `http://127.0.0.1:61006/`. Earlier windows continue using their previously loaded builds.
