# Tuxemon Chromatic Prototype

- [x] Ground: inspect fork, dialogue, device and toolchain.
- [x] Sketch: compare native ROM snapshot and MCU Wi-Fi client.
- [x] Agree: choose playable native ROM snapshot plus Python subscription companion.
- [x] Implement auth/providers and ROM generation in isolated output dirs.
- [x] Verify exact ROM buttons and dialogue in PyBoy.
- [x] Attempt subscription sign-in; consent screen reached, no grant, timeout recorded. Live ChatGPT inference remains pending user consent.
- [x] Try exact demo over USB, preserving cartridge and saves. Vendor success and process closure recorded. Physical screen/buttons await user observation.
- [x] Persist source, provenance, recovery notes and results in fork checkout.
- [x] Scrap: skip because the snapshot path compiles, runs in PyBoy, and completes a USB live demo.

## Throughput Checkpoint

- Blocking first steps: exact fork baseline and ready GBDK/PyBoy verified; ChatGPT inference depends on browser consent.
- Independent workstreams: auth/providers, ROM generator, hardware feasibility findings each use their own temporary directory.
- Shared mutable state: root alone integrates accepted artifacts and owns physical USB actions.
- Smallest safe decomposition: one owner for each independent artifact, root checks exact compiled result.

## Delivery

Local only. No branch, commit, push, PR or cartridge write is authorized. Native USB live demo requires no cartridge erasure. Direct custom MCU flash awaits a verified recovery path.

## Connected Companion and Firmware Preparation

- [x] Add paired HTTP/TLS companion endpoint and test real local Ollama request.
- [x] Correct release-age cutoff and pin policy-allowed final environment.
- [x] Build exact official ESP32 baseline, disabled prototype, and explicit experimental profile.
- [x] Fix accepted deep review findings and pass targeted rereview.
- [x] Preserve source/tools in durable ignored runtime paths and verify clean rebuilds.
- [x] Verify retained source/binary hashes against receipts.
- [x] Record uninstalled/unverified radio, layout, recovery, battery, and physical control limits.
- [ ] Pending external step: ChatGPT grant requires user confirmation; no grant assumed.
- [ ] Pending external step: custom firmware requires actual layout/recovery review and explicit installation authority.
