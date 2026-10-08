# Chromatic Verification Map

This map describes user paths in the conversation playground, not the full Tuxemon desktop game. For the terminal adaptation, start with [Terminal Interface](terminal.md); its PTY tests require no ROM bundle. For ROM work, start with a fresh helper-owned ROM bundle and a passing doctor. All commands run from the Tuxemon root. ROM commands use `VERIFY_RUN` set to the helper's actual emitted path.

- [Terminal Interface](terminal.md) covers real keyboard navigation, all nine editors, quest confirmation, and optional live Ollama drafting in isolated PTYs.
- [Screen Rendering](screens.md) covers the blinking regression, phase transitions, scrolling, and wait screens.
- [Drafting](drafting.md) covers all nine input methods, literal preview, deletion, and explicit Send.
- [World and Quests](world.md) covers walking, collisions, all four areas, five NPCs, item spending, and guarded progression.
- [Live Companion](live.md) covers real local classification, optional draft generation, and paired HTTP text.

For ROM paths, use only isolated headless PyBoy instances created by the helpers. Never drive an existing user game or choose an arbitrary localhost service. ROM evidence pairs the action, intermediate frames, and resulting state with the exact ROM digest. Record missed paths as gaps. Synthetic host boundary fixtures and real inference have separate proof labels. Physical display/control forwarding and handheld Wi-Fi remain outside this map.

The screen coverage manifest is enforced by the screen harness. When a new phase, method, or entry point appears in the ROM, add it to the manifest and recipe; do not relax coverage to make a test pass. Failure captures survive cleanup.
