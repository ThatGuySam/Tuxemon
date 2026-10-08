# Custom Tuxemon Game Cloud Handoff

Sam's explicit October 8 direction is to extend his existing Tuxemon fork into a custom playable Tuxemon environment, with the conversation input interfaces integrated inside the actual game. Do not make a new standalone game, terminal replacement, or separate ROM the primary deliverable. Existing Chromatic and terminal experiments are reusable references. Cloud tasks must continue independently while Sam's Mac is offline.

## Target and Existing Work

Repository: https://github.com/ThatGuySam/Tuxemon, start from the current published main checkpoint containing this document. Inspect current repository instructions first. The real game is Python/Pygame under `tuxemon/`, launched through `run_tuxemon.py`, with existing maps, entities, events and mod data under `mods/`. Read `README.md`, `docs/installation.md`, `docs/mods.md`, and the actual event/state architecture before selecting integration points.

`chromatic_demo/native/playground.c` and `worlds/last_ascent.json` implement a small standalone Game Boy test world with four areas, five NPCs and guarded quest choices. It is not the main Tuxemon engine. `chromatic_demo/terminal.py`, `terminal_state.py`, `providers.py`, and `TERMINAL.md` implement the later Mac text lab with live Ollama NPC replies, per-NPC conversation history, cancellation, exact preview and explicit game effects. Reuse domain logic where sound; preserve existing users and assets.

Nine input methods were researched and implemented: keyword chips, intent/topic/stance, initials shorthand, predictive grid, grouped alphabet, custom EdgeWrite, Dasher-inspired tree, radial groups, paired host/keyboard input. There were not twelve implemented methods; twelve native menu rows include Journal, Reset and Return. See `docs/research/chromatic-conversation-input-ux-2026-10-05.md` and `chromatic_demo/PLAYGROUND.md` for intent and documented approximations.

## Product Acceptance

A player launches the existing Tuxemon game into an opt-in custom scenario, walks around its real map, approaches real NPCs and opens a conversation using the normal game input/event path. An in-game menu selects all nine input methods ordered as in the research. Directional controls plus A/B/Start/Select suffice for the constrained interaction; optional normal keyboard entry can be switched on quickly. Selecting an item consistently activates it. Show the current controls and input mode. Preserve exact names, negation and quantities. Preview the exact outgoing message, then explicitly send it.

Ollama must answer as the NPC after Send, not merely rewrite the player's words. Keep optional outgoing-draft assistance separate. Preserve recent conversation history per NPC, maintain UI responsiveness, and retain unsent text on cancel/error/timeout. Never substitute canned text while claiming a live-model response. NPC text cannot award items or change quests; game effects go through existing game validation and explicit player action. Provide repeatable reset and comparison scenarios, including quantity/refusal, name correction, unknown words, competing needs and risky-route refusal.

NPC prose may be longer than one screen; paginate or scroll without hiding controls. The default environment is the existing Tuxemon renderer and maps. Keep Game Boy input constraints as an evaluation mode rather than pretending this desktop game is running on physical hardware. ModRetro firmware, cartridge erasure, flashing, partitioning, and physical connectivity are out of scope.

## Cloud Execution and Verification

Everything required to inspect, implement, build and run deterministic tests must be present in the cloud checkout. Do not depend on `/Users/athena`, local virtualenvs, local model snapshots, localhost on Sam's Mac, a running Mac window, pairing secrets or desktop tools. No API key purchase, paid model provisioning, ChatGPT credential reuse, hardware write, deployment or automatic merge is authorized.

Use a reproducible Linux test setup appropriate for this repo. For real game verification, use Pygame/SDL headless facilities or Xvfb and drive actual game input/state transitions through user-facing routes; retain rendered evidence and assert movement, NPC interaction, all nine editors, preview/send, follow-up conversation and guarded effects. Synthetic HTTP fixtures must be clearly labeled; they prove protocol behavior, not live inference. If an actual local-to-cloud Ollama service is unavailable, implement the real configurable adapter and deterministic HTTP tests, and report live inference as unverified. Never call a fake response a real model result. Retain dependency minimum-release-age rules if configured.

The earlier test gap was selecting with A programmatically while the human pressed Return. Tests must include the advertised keys from startup through actual conversation and a follow-up. Another live failure was the model echoing the player; `providers.py` now explicitly separates player input and NPC role. Preserve that contract. Do not rely only on reducer tests or terminal tests as proof of a Pygame integration.

## Work Ownership

One cloud implementation owner should deliver the integrated custom environment, all nine in-game editors, Ollama conversation adapter and implementation-specific tests as one coherent change set. A separate cloud verification owner may build independent actual-game launch/input/rendering baseline tests and an acceptance checklist in a disjoint test/document area. Each task uses its own cloud checkout/branch; never have independent workers push the same branch. Verification should not guess an implementation API or claim unimplemented features pass. Document integration points and any remaining assembly step so a later reviewer can combine the outputs.

Return reviewable cloud diffs or draft PRs with exact tests and known limits. Do not merge or deploy. Do not change unrelated game systems or delete the earlier experiments. The immediate handoff objective is to start cloud tasks successfully; work continues there without a local coordinator.
