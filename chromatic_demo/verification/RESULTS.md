# Prototype Verification

Verified October 5, 2026. Source checkout `/Users/athena/Code/Tuxemon`, origin `https://github.com/ThatGuySam/Tuxemon`, development baseline `9e6258ff726b786040a267e8bdbbf037b560285e`. New source is local and uncommitted.

## Observed Results

- 51 focused tests and four subtests passed with Python 3.14.6. Ruff passed using the fork configuration. Tests cover synthetic OAuth/JWT failures, refresh scope and identity, stream completion/error handling, real asset conversion, imported-source labeling, and reply bounds.
- Offline and Ollama GBC ROMs compiled using the installed GBDK 4.5.0.
- PyBoy 2.7.0 booted both exact ROMs and verified selection wrap, all three intents, all pages, A completion, and B cancellation. Build directories contain screenshots and `emulator-verification.json`. These are emulator screenshots.
- Local `gemma4:26b-mlx` returned three completed replies through the provider. The final provenance file contains prompts, displayed replies, the provider source hash, source asset hashes, generation timestamp, and ROM hash. The source hash and ROM hash were read back and matched. After a later empty-output guard, the measured snapshot's original provider source is preserved at `build/chromatic/ollama/provider-source.py`; it still matches the generation receipt.
- The final Ollama ROM is 32,768 bytes with SHA-256 `b347d799253cd731928453e6da3a79b3397eadfc900dc1aedf9823b63a9ae51f`. The plugin's public inspection validated the header and digest.
- A 90-second host-emulated USB demo to Chromatic Player 01 completed successfully. The vendor reported 90.00152275 seconds and `duration_elapsed`. The original process exited with code 0 and closed. [usb-result.json](usb-result.json) is the compact receipt. The complete private operation journal is at `build/chromatic/usb-demo-2026-10-05.jsonl`.
- The cartridge write was `not-dispatched`, save mode was `none`, and no MCU or FPGA firmware update was performed. USB playback is host emulation; native cartridge execution was not tested.

## Companion and Dependency Checks

The paired companion accepted one real loopback HTTP request and returned `source: ollama`, `fallback: false`, a matching request ID, and the correctly spelled Rockitten reply. `companion-probe.json` records the response. The listener was closed after the probe. No LAN listener remains running.

The full 51-test suite includes real loopback HTTP/TLS checks using synthetic certificates and pairing secrets, authentication/schema rejection, fallback behavior, and empty sanitized provider-output rejection. Source lint passed after the repository import-order fix.

The initial dependency cutoff used September 28 at end of day and admitted PyJWT 2.15.1 before a full seven days had elapsed. A stricter September 28 00:00 UTC resolution rejected that version. The final environment and requirements use policy-allowed PyJWT 2.15.0; focused tests passed after replacement. `requirements-lock.txt` and `python-environment.txt` record the allowed final environment.

## ChatGPT Sign-In

The local PKCE callback started and the official browser flow reached the consent screen for Tuxemon Chromatic Prototype. New access to basic profile and ChatGPT plan allowance needed user confirmation under browser controls. No grant was approved during this run. The listener expired after three minutes, and its stale browser tab was closed. Safe auth status returned `connected: false` and `plan_usage: false`. The companion retains a private host identifier for a fresh login, outside source. No token values were inspected or logged.

Real ChatGPT inference, account eligibility, refresh, and revocation remain unverified. Synthetic contract tests do not establish live account success. No API key or billed fallback was used.

## Gaps and Next Checks

The physical screen and buttons were not independently observed and await Sam's feedback. The successful vendor receipt verifies the USB operation, not the viewed display or controls.

The optional MCU Wi-Fi dialogue client is implemented and compiled in a separate experimental profile, but remains uninstalled and untested on hardware. Direct RF, live handheld-to-model dialogue, the cartridge-to-MCU mailbox, and custom firmware recovery remain unverified. The experimental image requires a larger app partition and separate layout/recovery approval. See [firmware/README.md](../firmware/README.md) for its implementation and build evidence.

One generated reply spells Rockitten as Rockkitten. The prototype preserves this real output in provenance. Character filtering and length bounds do not validate factual accuracy or child suitability. Review generated copy before sharing it.

## Design and Review

The native snapshot route was selected over a direct MCU Wi-Fi client because the installed Game Boy toolchain already builds and runs a scene. The MCU path lacks a prepared firmware toolchain and a verified recovery/RF baseline. Python matches Tuxemon; a small C renderer uses GBDK. Rust would add a runtime and bindings without removing this milestone's blockers.

Model the Domain shaped explicit provider and screen states. Prove It Works required testing the compiled ROM and retaining the original USB completion receipt. Independent GPT-6 Luna review supported the native route and flagged stale progress records and prompt-only child-suitability claims. Progress records now include the observed results; the suitability boundary is explicit above. The review did not find an actionable credential exposure in the implemented flow.

No task branch, staging, commit, push, PR, merge, deployment, publication, or external message was performed. Existing Tuxemon engine/content files and unrelated notes-search work were preserved.

## Reviewed Firmware and Durable Toolchain

The original MCU baseline, modified feature-disabled profile, and enabled experimental profile passed ESP-IDF v5.3 compile/link and partition-size guards. The first enabled build correctly failed the stock 1 MiB size guard. A separate build-only 2 MiB app profile preserves source-table NVS/PHY offsets. It has not been written to the device.

Deep review by the resolved gpt-5.6-sol model found certificate-date validation, sleep-transition, plaintext NVS, and text-layout issues. Fixes were applied and rebuilt: certificate date checking and successful SNTP now gate HTTPS; experimental builds skip manual sleep before FPGA/OSD changes; credentials are RAM-only; wrapped text uses actual LVGL font/layout metrics and A pagination. Targeted rereview found no actionable remaining findings in those fixes. RF, UI, serial, battery, and TLS behavior on the physical unit remain unqualified.

The source and tools now live under `/Users/athena/Code/Tuxemon/venv/chromatic-firmware/`, which Git ignores. The Python 3.13 environment retains all 57 exact dependency versions with the strict release-age cutoff. Both clean builds passed again after relocation. SDK configurations and reviewed source hashes remained identical. Durable builds embed normalized SDK paths, so their binary bytes and sizes differ from historical artifacts.

The relocated feature-disabled image is 781,200 bytes. The relocated enabled experimental image is 1,321,632 bytes. `firmware-persistence.json` verifies the actual retained binaries against their relocation receipt and rechecks reviewed source hashes. Binaries, maps, logs, and earlier superseded evidence are saved under ignored `build/chromatic/firmware/`. The reviewed patch and receipts are saved under `chromatic_demo/firmware/`.

Installation is not approved. No custom MCU or persistent FPGA firmware installation, partition-table write, radio scan/connect, physical serial provisioning, or recovery test occurred. Read-only USB discovery and the earlier USB live demo were the only device operations from this chat.
