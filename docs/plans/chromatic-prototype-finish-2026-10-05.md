# Finish the Playable Prototype

Exit condition: CI succeeds for the exact main SHA; every one of nine conversation interfaces completes a real input/preview/send/interpret/reply flow in the owned Mac game; the full guarded quest and item spending pass; all required source is pushed to main. Preserve existing sessions. Stop before any cartridge erasure or firmware installation.

## Progress

- [x] Inspect current source, remote head, goal, and hosted CI failure.
- [x] Reproduce pytest-console import failures locally; package discovery includes only tuxemon.
- [x] Repair editable-package discovery and verify installed imports outside checkout.
- [x] Run CI-equivalent collection/tests, packaging checks, and scoped guards.
- [x] Audit and prove all nine complete interface flows, including actual paired browser input.
- [x] Prove full quest progression and item guards against the final compiled ROM.
- [ ] Commit and fast-forward main; verify exact remote SHA.
- [ ] Observe CI success for that exact SHA and audit completion.

## Work Boundaries

The root owns persistent source changes, publication, and goal status. The native harness owner audits interface-flow coverage in its isolated checkout. Verification creates its own emulators and ephemeral loopback server. Existing user game windows, browser tabs, and physical sessions are preserved. No paid API or sign-in grant is required. The physical Chromatic/Wi-Fi milestone remains outside this goal.

## Evidence and Decisions

Hosted main at 2393c15 passed lint but failed test collection because chromatic_demo was unavailable to the installed tox environment. Local console pytest reproduced seven import failures. The current setuptools package filter includes only tuxemon*. The first experiment is installing and importing the actual distribution in a fresh isolated environment; changing pytest search paths would not prove that the installed prototype package works.

CI-equivalent full-suite iterations exposed the repository named-parameter guard and a provenance unit test depending on an absolute Mac path and installed GBDK. Parameter inputs now use descriptive pytest.param IDs. The provenance unit test resolves the actual checkout and uses an explicitly synthetic compiler boundary; actual ROM compilation remains required by the frame/quest gates. The first repaired full run reached 4,489 passing tests with only that compiler-dependent unit failing. No native runtime behavior was changed.

Final runtime audit: nine complete conversations using actual local GLiClass receipts and paired HTTP passed 655 actions and 13,083 checked frames. The full screen gate passed 39,273 frames. The actual paired form produced exact Preview and a real-model confirmed authored reply through an owned browser tab. Full quest returned flags255/inventory12. All receipts name the exact same ef806 ROM. CI repair8ad722b is already green remotely; final verification-source publication and exact final CI remain to be checked.
