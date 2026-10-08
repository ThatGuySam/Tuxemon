# Shared UI Redraw Fix

The previous correction covered same-area walking. Menus and editors still call the shared clear-before-paint renderer. Root reproduced menu Down in the actual compiled ROM: frame seven was entirely blank, and the menu heading disappeared in frames three through seven.

## Progress

- [x] Reproduce it yourself on the matching surface.
- [x] Binary-search the cause. Shared blanking is visible before repaint; movement uses a separate corrected path.
- [x] Plan the fix. Compare a RAM tile canvas and background map buffering, then remove visible clearing from all shared screens.
- [x] Verify on the same surface. Check every intermediate frame during menu scrolling, all editors, preview, meaning selection, reply pages, and world changes.
- [x] Verify exact deletion and shorter text clearing, map/assets, memory layout, prior movement regressions, and live mailbox integration.
- [x] Review frozen source and build, then start the corrected local game.
- [x] Save before/after evidence and delivery status.

Staging, commits, PRs, and cartridge flashing are skipped because no publication or erase acknowledgement was requested. Keep prior running game sessions intact. Root owns persistent copies; native author and reviewer work against their existing isolated checkout. The prior build is preserved at `build/chromatic/playground-before-ui-fix/`.

## Delivery

Root rebuilt and verified ROM `ef806f6a27c18cdf9da86562c6691612307691681f7a1d9ecb24953955b4282e`. A fresh corrected Mac game was started, preserving older sessions. The prior b9b54 build is historical at `build/chromatic/playground-before-ui-fix/`; earlier windows keep running their original ROM. Source and verification are local and uncommitted.
