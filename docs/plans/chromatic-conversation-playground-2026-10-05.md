# Walkable Conversation Playground

Build a playable late-game conversation test slice with all nine researched input approaches, ranked by current design judgment. All new story material is authored game fiction. Classification means a GLiNER-family picker, not JEPA/world-model inference.

## Plan and Progress

- [x] Ground: inspect current ROM, companion, research and public USB transport.
- [x] Sketch: compare standalone native game and owned-PyBoy live bridge.
- [x] Agree: one ROM with explicit authored standalone and live companion modes.
- [x] Author four connected areas, five NPCs, guards and meaningful quest consequences.
- [x] Implement all nine functional composers and readable game navigation.
- [x] Integrate real cached GLiClass classifier and optional Ollama composition.
- [x] Verify all input methods, movement, collisions, draft preservation, commit/cancel and quest progression in the compiled ROM.
- [x] Verify paired HTTP text and one real classifier round trip through ROM mailbox.
- [x] Review exact source/artifact; fix accepted findings and reverify changed behavior.
- [x] Demo approved ROM by USB; permanent cartridge write waits for required erasure acknowledgement.
- [x] Save build, test, model provenance and operating instructions.

## Throughput Checkpoint

- Blocking first steps: current workspace/data integrity and public transport checked.
- Independent workstreams: native ROM/compiler owner, companion owner, classifier owner and scenario author each use their own isolated output directory.
- Shared mutable state: one agreed mailbox/content contract; root alone copies completed outputs into the fork and owns physical operations.
- Smallest safe decomposition: one native owner prevents conflicting C state/render changes; host workers remain independent until interface contracts stabilize.

## Behavioral Contract

The native world owns quest and inventory state. Every outgoing message is editable and explicitly previewed/sent; semantic interpretation is confirmed before consequential quest changes. Unknown or low-confidence classification leads to clarification. Model and authored outputs carry distinct source labels.

Method IDs remain intent0, keywords1, shorthand2, grid3, grouped4, gestures5, predictive tree6, radial7, paired8. Visual ordering starts with keywords, then intent. The ranking is a research judgment, not measured user preference.

The versioned TXMB WRAM mailbox occupies C800..CBFF. Worker results require matching sequence/context/draft revisions and session nonce. Only the emulator thread reads/writes RAM. Native USB streaming has no documented live model callback, so it uses authored behavior. Paired text is real in the owned emulator and explicitly unavailable in standalone mode.

## Delivery Authority

Build and local prototype deployment are authorized. No GitHub branch, commit, push, PR or cloud publication is requested. Cartridge flashing is a separate destructive operation; the Chromatic skill requires acknowledgement that it erases the selected cartridge and may lose saves without backup. Build the concrete reviewable ROM before requesting that acknowledgement. Custom MCU repartitioning remains outside this ROM deployment.

## Verified Delivery State

The exact 32,768-byte ROM is `build/chromatic/playground/playground.gbc`, SHA-256 `0c5bf99c0d119bf2de354b60b2e5546a879c2091b46e0b00dc5f6b1f9bc1c58a`. Native button-driven verification, all WRAM/layout guards, real GLiClass/Ollama/paired mailbox integration, scoped tests, and independent final review passed. The two-minute USB operation succeeded with no cartridge write. The owned Mac SDL2 game and loopback paired input server were started for user play.

Permanent cartridge installation waits for the explicit game/save-loss acknowledgement requested in chat. No firmware, Wi-Fi provisioning, Git publication, or ChatGPT plan connection is claimed. Model quality remains weak on the current 25 authored development fixtures, with six exact expected matches; scores are uncalibrated and all effects require confirmation.
