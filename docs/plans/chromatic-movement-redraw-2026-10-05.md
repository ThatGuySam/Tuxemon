# Movement Redraw Fix

The user supplied a screen recording showing a white flash on each player step. Extracted frames show the entire world cleared and then partially repainted. Native `render_world()` calls `blank()` for every pressed input, hiding sprites and writing spaces across the visible background.

## Progress

- [x] Inspect the actual recording and current renderer.
- [x] Reproduce on the exact compiled ROM with a frame-by-frame movement trace.
- [x] Isolate full-background clear and sprite hiding as the mechanism.
- [x] Update same-area world movement through sprite position and changed interaction hint only.
- [x] Run the original frame-by-frame repro, blocked and held movement, all editor/quest checks, and independent review.
- [x] Build and start the corrected game without erasing the user's existing running session.
- [x] Save before/after evidence and operating status.

Git staging, commits, and PRs are skipped because the user requested a local fix and demo, not publication. No cartridge flash or firmware write is authorized by this bug report. The existing ROM and receipts are preserved under ignored `build/chromatic/playground-before-movement-fix/`.

## Delivered Artifact

Corrected ROM SHA-256 `b9b54bf6d16cfbaf562b8ed1d0f65a085d7e22e7788697c844d0d6005df6bc93`. Root rebuilt and reran movement frames, full native gameplay, layout checks, and scoped lint. Independent review accepted. A fresh Mac game was started; the prior running session was preserved. No cartridge write or Git publication occurred. See `chromatic_demo/verification/movement/RESULTS.md` for exact proof boundaries.
