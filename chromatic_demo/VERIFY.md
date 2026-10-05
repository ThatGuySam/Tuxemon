# Chromatic Conversation Verification

This bundle includes the walkable conversation ROM, its Mac companion, and a project-local `verify` skill. Four authored areas and nine input modes provide a repeatable setting for screen and interaction checks. The native renderer prepares each screen in RAM and updates changed background tiles without clearing the visible display first.

## Set Up

From the repository root, prepare Python 3.10 or later and the ModRetro plugin's GBDK toolchain:

```sh
uv venv venv/chromatic --python python3
uv pip install --python venv/chromatic/bin/python --exclude-newer '2026-09-28T00:00:00Z' -r chromatic_demo/requirements-dev.txt
```

The cutoff preserves the seven-day release-age policy for this October 5 setup; use an equivalent age cutoff for later installations. The installed macOS compiler is discovered under the current user's `Library/Application Support/modretro-chromatic/toolchain/.local/gbdk/bin/lcc`. Set `GBDK_LCC` for another compiler location. Model weights are optional and are not part of the repository.

## Run the Code Gate

```sh
VERIFY_RUN="$(.agents/skills/verify/scripts/control.py launch | sed -n 's/^RUN=//p')"
test -n "$VERIFY_RUN"
.agents/skills/verify/scripts/control.py doctor --run "$VERIFY_RUN"
.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature screens
.agents/skills/verify/scripts/control.py cleanup --run "$VERIFY_RUN"
```

Every drive uses an independent headless PyBoy instance. It checks each driven frame for blanking, disabled LCD, or disappearing persistent content. Coverage is required for every compiled phase and input mode plus the declared interaction paths. Missing coverage fails. Optimized Python cannot disable these assertions silently.

Receipts, action/frame logs, failure captures, and the exact compiled ROM remain under the emitted run directory. Current-ROM verification passed 1,632 actions and 39,273 frames across eight states, nine methods, four areas, and 48 required paths. The preserved historical blinking build failed at frame seven with zero dark pixels. That negative control needs the exact local historical bundle; a fresh clone without it reports the missing prerequisite rather than fabricating evidence.

Read [.agents/skills/verify/SKILL.md](../.agents/skills/verify/SKILL.md) for the maintained feature map, world and optional live-model commands, teardown, and proof boundaries. [PLAYGROUND.md](PLAYGROUND.md) documents controls and scenarios. Historical raw frames and firmware experiments remain local; the committed verification summary describes the actual local runs.

The default repository test environment installs the lightweight companion dependencies. The actual pinned-model integrity test explicitly skips when the optional snapshot is absent. Model quality is separate from rendering correctness; scores remain uncalibrated and interpretations require player confirmation.

## Attribution and Scope

New code is GPL-3.0-or-later. Professor overland art is by Kurt Stine; Rockitten overland art is by tamashihoshi. Both use CC BY-SA 4.0 as recorded in the fork's `ATTRIBUTIONS.md`. The builder crops and converts these assets into Game Boy tiles. Preserve source and credits when sharing the ROM.

The new story is authored test fiction, not canonical Tuxemon endgame. Emulator evidence does not prove physical display behavior or handheld Wi-Fi. No cartridge or custom firmware installation is part of this verification workflow. Source publication, CI completion, deployment, and physical playback are separate states.
