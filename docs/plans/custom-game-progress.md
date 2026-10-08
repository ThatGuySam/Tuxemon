# Custom game cloud implementation

Base: origin/main 6d3fb1e7b4590183b53a33f7d6ff86aa39e87c00.
Owner branch: codex/custom-tuxemon-cloud, isolated checkout /workspace/work/tuxemon-custom.

## Plan and progress

- [x] Read handoff, installation/mod docs, WorldState, state manager,
  input translation, TMX event conditions, NPC creation and item actions.
- [x] Add opt-in TMX camp with five real NPCs and normal interaction events.
- [x] Complete Pygame conversation overlay, nine editors and Ollama lifecycle.
- [x] Drive actual engine with SDL/Xvfb; cover advertised activation keys,
  editors, HTTP protocol, history, cancellation, errors and guarded items.
- [x] Retain renders, reproducible setup, reviewable diff and limits.

## Decisions

- Existing WorldState, map renderer, movement/collision managers, NPC entities,
  event engine and bag remain authoritative. Current campaign startup is unchanged.
- Extract the checked-in prototype composer into a game-owned module. Preserve
  the researched approximations and exact preview. No account auth imports.
- Scenario quest items are namespaced engine items; authored guards are checked
  again on explicit confirmation. NPC prose cannot call engine actions.
- Configurable /api/chat adapter requires an explicit endpoint/model. No fallback
  answer is substituted on missing configuration or failed inference.
- All work stays in cloud. Synthetic HTTP evidence will be labeled. Live
  inference remains unverified unless a real cloud Ollama service is available.

## Validation progress

- Actual SDL launch renders the TMX camp and five NPC entities. Real key presses
  walk from spawn to Professor and open the overlay with Return.
- Complete acceptance now exercises all nine editors with both Return and the
  engine controller A input, previews, Send and follow-up, paged long NPC prose,
  synthetic HTTP errors, malformed replies, cancellation and socket timeouts.
- All five NPCs are approached by walking. Tests verify separate confirmations,
  one-pack exchange and repeat refusal, name correction, safe-route prerequisite,
  risky-route refusal, permit issuance, aid-kit refusal/use and repeatable reset.
- Repository-local setup rebuilt a separate venv from the lock resolved with
  cutoff 2026-10-01T00:00:00Z. Existing configured seven-day age policy is retained.
- 122 existing config/input/map-event/map-manager/NPC-manager tests passed.
- Xvfb acceptance passed, 6 tests, 73.22 seconds. Final cancellation lifecycle
  hardening is being rechecked with SDL and Xvfb before packaging.
- No live cloud Ollama is configured. All inference screenshots explicitly show
  SYNTHETIC HTTP FIXTURE. Physical controller hardware is unverified.
- Five separately authorized supplementary tasks own their specified paths.
  This implementation does not edit or depend on those directories.

## Final implementation decisions

- Overlay remaps only its own keyboard context. Shift stays the normal capital
  modifier while typing; controller B still backs out. Physical BACK/Select and
  Tab toggle typing. World input middleware and original mappings are restored.
- One worker and result queue belong to the scenario, so reopening an overlay
  cannot launch concurrent cancelled requests. Request snapshots reject late,
  stale or differently scoped results. Drafts survive errors and map round trips.
- A reconstructed scenario reads existing engine flags/items and does not reset
  them. Full disk save/resume and conversation persistence remain outside this
  verification claim; the separately authorized audit can inspect that area.
- No push, merge, deployment, model provisioning, account credential reuse,
  hardware access or supplementary-task path edits were performed.

- Existing gettext cache reproduction failed before the compiler fix. Invalidating
  exactly the newly compiled catalog now lets added quest-item translations pass
  database validation in existing installations. Regression added and passed.
- Final SDL acceptance: 7 passed, including real Shift capital typing and engine
  state reconstruction. Final Xvfb is running from the repository's own rootless
  installation rather than relying on the environment bootstrap binaries.

- Both real CLI routes were verified with finite actual-client loops: `--custom-game`
  walked to and opened the Professor, while no flag retained normal Splash/Intro
  startup. Captures and machine-readable route reports are retained.
- Rootless Xvfb package extraction and Python setup were both rerun successfully
  using the checked-in scripts. Apt hooks are isolated to avoid global cache writes.

## Completed verification

- Final actual-game and compatibility suite: 7 passed in SDL, 13.36 seconds;
  7 passed in repository-installed Xvfb, 74.10 seconds.
- Final existing-engine regression selection: 122 passed, 3.39 seconds.
- Both real CLI startup routes passed finite actual-client smoke checks.
- Ruff, formatting, shell syntax and git whitespace checks passed.
- Reviewed screenshots, JUnit results, setup/test logs and a labeled evidence
  gallery are checked in under docs/custom-game/evidence.
- Review package will include a binary-capable diff against the exact base.
  It is delivered without a push, merge or deployment.
