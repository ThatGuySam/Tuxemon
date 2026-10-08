# Chromatic Verification Skill

Create a project-local Codex `verify` skill and executable driver for the compiled conversation ROM. The screen gate must cover concrete paths through every ROM phase and input method, observe every driven frame, and reject the preserved blinking build for its actual rendering failure.

## Progress

- [x] Interview the repo, not the user. Ground the primary ROM surface, optional local model/HTTP companion, existing builder and PyBoy harnesses, and instance isolation.
- [x] Generate the skill. Create `.agents/skills/verify/SKILL.md` and its executable controller; validate frontmatter and invocation.
- [x] Seed the feature map. Document screens, drafting, world/quests, and live companion with observable paths and explicit gaps.
- [x] Prove launch, doctor, world drive, and cleanup through the generated helper. Independent cold trial passed and evidence survived cleanup.
- [x] Fix observed helper timeout retention and harness teardown gaps; narrow unsupported collision claims in the map.
- [x] Run the comprehensive screen gate through the helper, including all phases and methods, real paired HTTP, and labeled host boundary fixtures.
- [x] Prove the historical negative control fails for white-frame/header erasure, retain failure evidence, and clean up.
- [x] Recheck generated skill, feature map, and executable helpers against observed receipts; save delivery proof.
- [x] Offer the maintenance loop through `/maintain-verification-skill`.

Native game behavior, user GUI/browser sessions, physical devices, credentials, and Git publication remain outside this task. Root owns helper/skill files; the existing native harness owner upgrades only the screen verifier in its isolated checkout. Each verification command owns a fresh headless emulator and disposable loopback endpoints. Evidence is retained under the helper's UUID run directory.

## Verified Delivery

The generated skill passed end-to-end use. Complete screen coverage: 8 phases, 9 methods, 4 areas, 48 paths, 1,632 actions, 39,273 checked frames. The old blinking ROM failed specifically for an all-white frame. Cleanup retained all proof. Delivery report is `chromatic_demo/verification/skill/RESULTS.md`; source and docs remain local and uncommitted.
