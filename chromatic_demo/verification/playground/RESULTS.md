# Initial Playground Verification

The latest movement correction is recorded in [Movement Redraw Fix](../movement/RESULTS.md). The initial records below describe the earlier build.

The source and ROM are local and uncommitted in Sam's Tuxemon fork. This is an original authored late-game test slice, not a port of the full canonical endgame.

## Exact Artifact

The initial artifact, preserved at `build/chromatic/playground-before-movement-fix/playground.gbc`, is 32,768 bytes. SHA-256 is `0c5bf99c0d119bf2de354b60b2e5546a879c2091b46e0b00dc5f6b1f9bc1c58a`. Build provenance records the compiler, assets, canonical world, generated C, ROM digest, and actual NOI/MAP layout. The mailbox occupies C800 through CBFF without overlapping allocated game RAM.

## Observed Checks

- 51 existing prototype tests and four subtests passed in the original Python 3.14 environment.
- 33 classifier/bridge tests passed in the installed Python 3.13 environment, including authenticated loopback TLS and zero-length PyBoy mailbox reads.
- Scoped Ruff passed for all prototype source and tests.
- Actual PyBoy buttons exercised eight distinct local editors, all 95 printable ASCII characters, exact previews, explicit Send, draft preservation, cancellation, stale results, collisions, world traversal, item spending, guarded outcomes, and the complete quest.
- Build verification rejected 22 authored invalid-content and memory-layout fixtures. These are regression tests, not measured hardware outcomes.
- The persistent real integration verifier passed GLiClass classification, actual paired HTTP input, completed Ollama composition with `gemma4:26b-mlx`, and unavailable-picker authored fallback. Inventory and quest flags remained unchanged until meaning confirmation. Preview did not Send.
- Independent final review accepted the frozen source and ROM after fixes. No remaining actionable findings were reported.
- The public USB operation succeeded for the requested 120 seconds, with vendor success and process closure. Cartridge writes were not dispatched. Its operation ID is `5dd7fa613069ddfe8df9aa6bf0371d348442ee6a0ef6665e94f923dec7a808db`.

The native verifier's host response fixtures are synthetic protocol tests. Separate `real-model-rom-e2e.json` records actual model and authenticated HTTP results. Physical display, audio, and button forwarding were not independently observed.

## Model Quality and Provenance

The classifier is `knowledgator/gliclass-edge-v3.0`, revision `df03993a2ed98e5e4a0d2dd7efbbd105abe874cf`. All five model/config/tokenizer files are checked against source-pinned digests before attaching that identity. Safetensors and offline loading are required. Exact dependency versions and hashes are retained in `requirements-picker.lock`, with installation cutoff `2026-09-28T00:00:00Z`.

The current canonical-label run matched six of 25 authored expected labels. This local development fixture run is not a held-out accuracy benchmark or user study. Earlier probes used different labels or candidate filtering and do not describe the delivered pipeline. Scores are uncalibrated; the 0.80 score and 0.03 margin gates are prototype policy. The picker is advisory. Confirmation and manual meaning selection remain necessary.

Ollama writes the player's outgoing draft; NPC response prose and quest effects remain authored. Exact generated text, actual model identity, and scores are retained in the real integration receipt. Generated wording still needs review for names, negation, quantities, and commitments.

## Running and Pending

An owned SDL2 Mac game with the real picker, Ollama, and loopback paired entry was started. Its actual endpoint is `http://127.0.0.1:57133/`. The private pairing file is `/private/tmp/last-ascent-session/pairing.secret`; its contents are not included in this record. The directory has owner-only permissions. The bridge runs only while this local game process is open; Escape closes the game and its server. Important source and reproducible outputs are in files. Test progress is intentionally session RAM, with reset and restart clearing it.

Eight local methods work on the physical USB route with authored behavior. The ninth, live paired text, requires the owned Mac emulator. The public vendor USB stream has no documented model/RAM hook. Direct handheld Wi-Fi and custom firmware remain uninstalled. ChatGPT plan access remains unconnected. No API key or paid API fallback was configured.

Cartridge flashing awaits explicit acknowledgement of erasing the existing game and possible save loss without backup. No cartridge, MCU, partition-table, Git, PR, or cloud publication action occurred.

[Operating guide](../../PLAYGROUND.md) and [ranked actual interface frames](DEMO.md) describe controls and realistic scenario routes. The JSON receipts in this directory preserve the proof boundaries above.
