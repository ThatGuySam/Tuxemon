---
name: verify
description: Verify the Chromatic terminal through real PTY keyboard input or the ROM through real PyBoy buttons. Use for menu/editor regressions, input methods, quest progression, or live Ollama checks in chromatic_demo.
---

# Verify the Chromatic Playground

For the Mac terminal adaptation, use [Terminal Interface](features/terminal.md): its launch, doctor, drive, evidence and cleanup steps use the real curses executable in isolated PTYs. This path needs no ROM build or device.

The remaining instructions drive the compiled Game Boy Color ROM, not the full desktop Tuxemon engine. Read [the feature map](features/README.md) before selecting a path. The primary surface is the 160 by 144 ROM screen; the Mac companion is secondary. Physical Chromatic display and USB control forwarding require separate observations.

## Launch

Run from the Tuxemon repository root. Existing dependencies are `venv/chromatic/bin/python`, PyBoy/Pillow, and the installed ModRetro GBDK compiler. The helper uses the documented playground builder and creates a fresh bundle under ignored `build/chromatic/verification/`.

```sh
VERIFY_RUN="$(.agents/skills/verify/scripts/control.py launch | sed -n 's/^RUN=//p')"
test -n "$VERIFY_RUN"
.agents/skills/verify/scripts/control.py doctor --run "$VERIFY_RUN"
```

The emitted `RUN=` path identifies the only bundle this run owns. `doctor.json` with `ready: true` confirms that its digest matches build provenance and the exact ROM boots to WORLD with TXMB v1 and a visible LCD. Every drive starts its own headless PyBoy; there is no persistent GUI process or fixed server port. Existing user games, paired tabs, and device reservations are untouched. Do not install dependencies or bypass release-age policy as automatic recovery.

## Doctor

```sh
.agents/skills/verify/scripts/control.py doctor --run "$VERIFY_RUN"
```

Use this first when a path behaves unexpectedly. It boots an independent emulator and checks the actual ROM, not a cached screenshot or a window title. A failed digest, boot, or handshake blocks further driving. Diagnose the saved stdout/stderr instead of changing a user session.

## Drive

```sh
.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature screens
.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature world
```

`screens` is the required screen-regression gate. It exercises enumerated ROM phases and input modes, asserts every driven frame, and fails on missing required coverage. `world` adds movement, full quest/item guards, and actual linker-layout checks. Read each mapped feature for the asserted entry points. A path not visited is not verified through another path.

The complete conversation-flow gate uses the installed picker environment and model snapshot. It drives each of the nine actual entry mechanisms through exact Preview, explicit Send, Meaning, and an authored NPC reply, with no item or quest effects before confirmation.

```sh
.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature interfaces
```

The optional live companion path uses the separate installed classifier environment and pinned local snapshot. It calls local Ollama, never ChatGPT account tokens or a billed API. It reads the selected run's ROM and writes its own evidence.

```sh
.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature live
```

For a rendering regression, run the negative control when the preserved historical bundle exists:

```sh
.agents/skills/verify/scripts/control.py negative-control --run "$VERIFY_RUN"
```

This requires the exact recorded b9b54 historical ROM. The helper succeeds only when the screen harness rejects that ROM for a white frame or erased heading. An unrelated crash is a failed negative control. Never reconstruct or fabricate historical evidence when the bundle is missing.

## Evidence

Commands, exit codes, stdout, stderr, ROM/provenance, coverage, action traces, and screenshots survive under the printed run directory. `screens/` contains intermediate LCD evidence and failure captures. Optimized Python cannot silently skip assertions: the screen script rejects `-O`, and the helper clears `PYTHONOPTIMIZE` for owned children. Core assertions check enabled LCD, nonblank frames, and persistent actual pixel regions during navigation, alongside typed text and game effects.

Exercise real buttons, actual walking, and actual paired HTTP input. Reading NOI symbols for observation is allowed; writing game-state fields to reach a screen invalidates a user-path proof. Clearly label host delay/error boundary fixtures as synthetic. They establish wait/cancel/error rendering, not real model inference. The separate `live` path records real model results. Session RAM is intentionally disposable and save writing is disabled. No probe, flash, firmware write, Git publication, or external send is part of this skill.

The test covers its maintained entry-point manifest, not every possible input history. A pass does not establish physical playback or atomic scene transitions. Large scene changes may update over several frames while retaining visible content.

## Cleanup

Run after every successful or failed iteration:

```sh
.agents/skills/verify/scripts/control.py cleanup --run "$VERIFY_RUN"
```

Each harness closes its owned emulator with `save=False`; paired tests stop only their own loopback server and worker. The helper's subprocesses are short-lived. Cleanup records retained evidence and verifies that files remain. It never kills by process name or closes a user's SDL window, browser tab, server, or physical device session. Retain failed-run evidence for diagnosis.

## Helpers

[Executable control.py](scripts/control.py) provides `launch`, `doctor`, `drive`, `negative-control`, and `cleanup`. Its `--help` describes the same commands. It locates the repository relative to itself and accepts only run directories it created under the verification root.

Use `/maintain-verification-skill` when app entry points change. Update the feature map and coverage manifest together.
