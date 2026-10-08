# The Last Ascent inside Tuxemon

This opt-in scenario extends the existing Python/Pygame engine. It uses a TMX
camp, WorldState, the map renderer, normal movement and collisions, five real
NPC entities, and the normal INTERACT event path. Existing campaigns keep their
startup route. The terminal and ROM experiments remain intact.

## Setup and launch

From the repository root, with Python 3.12 and uv installed:

```sh
bash scripts/setup-custom-game.sh
SDL_AUDIODRIVER=dummy work/venv/bin/python scripts/cloud_game.py run_tuxemon.py --custom-game
```

The repository runner puts config, caches and saves under `work/userdata`, never
in a home directory. The normal desktop entry point also accepts `--custom-game`:

```sh
python run_tuxemon.py --custom-game
```

For a real Ollama service reachable **from this cloud executor**, explicitly set:

```sh
export TUXEMON_OLLAMA_URL=https://your-ollama-origin.example
export TUXEMON_OLLAMA_MODEL=your-installed-model
```

The adapter calls `/api/chat` with distinct system/NPC and player roles. It makes
no request until explicit Send. Missing configuration, HTTP/protocol errors and
timeouts retain the draft. No account authentication, model purchase, automatic
model download, player-draft generation or fake fallback is used. A remote service
must be permitted by the cloud network policy. No service on Sam's Mac is assumed.

## Playing

Walk with arrows or a controller D-pad. Face one of the five expedition members
and press Return or A. F1/Start opens the conversation menu. Tab/Select switches
normal typing immediately. Escape/B goes back. Shift also acts as B in D-pad mode; in keyboard mode it types capitals. Backspace deletes. In the
conversation overlay, the controller's BACK/Select input toggles typing; keyboard
Escape remains B. The keyboard mapping and world middleware are restored on exit.

The Input methods menu has the nine researched methods in their original order.
Their names describe approximations, not claims of full standard implementations:

| Method | In-game interaction |
| --- | --- |
| Keyword chips | Choose exact words, including `not`; SPELL handles unknown words. |
| Intent composer | Choose intent, topic and stance, then inspect generated text. |
| Initials shorthand | Type or SPELL word initials, then activate a matching authored utterance. |
| Predictive grid | Arrows select characters; COMPLETE offers deterministic vocabulary completion. |
| Grouped alphabet | Choose a five-character group, then a character. |
| Custom EdgeWrite | Trace up/right/down/left, then A. This is a custom gesture table. B leaves the trace area for actions. |
| Dasher inspired tree | Choose and narrow one of four character branches. There is no gaze tracking. |
| Radial groups | A direction selects a group; A enters it, then selects a character. B leaves the radial area for actions. |
| Host / keyboard | Normal keyboard input in this same game window. SPELL remains available through the controller. No network pairing is implemented. |

Every editor has DEL, PREVIEW, SPELL, CANCEL, KEYBOARD and QUEST ACTIONS. In the
character grid, left/right advances one cell; up/down advances ten. Uppercase,
numbers and punctuation are available through SPELL and PAGE. The comparison
scenario accepts at most 96 printable ASCII characters. It rejects overflow or
unsupported characters visibly instead of dropping or normalizing them.

PREVIEW displays a quoted representation of the exact outgoing draft, including
spaces, names, punctuation, quantities and negation. Only the Send row requests
an NPC reply. Back to editing changes no text. NPC replies page with left/right,
while controls and Continue conversation remain visible. Replies are bounded to
8192 characters and 64 KiB HTTP payloads. Requests have a 15-second deadline and
socket timeout. The deadline is checked between reads; a blocked read can take
one further socket-timeout interval to finish. Cancellation invalidates the request immediately; the bounded
network operation finishes in a daemon worker. Late results cannot overwrite a
new draft or NPC conversation. A second worker is not launched while a cancelled
request is still finishing, including after closing and reopening the overlay.

Each NPC retains its own draft and up to 20 successful conversation turns for
this client session. Follow-up prompts include bounded recent history and current
authored quest facts. History and drafts are not persisted across game restart.
Start > Reset story explicitly clears story flags, scenario items, every NPC's
history and drafts. It is repeatable and leaves campaign data outside this
namespaced scenario alone.

Quest actions are a separate menu and confirmation, available even without a
model. Sending prose changes no items or flags. Confirmation rechecks authored
requirements, forbidden flags and actual engine inventory, then uses Tuxemon's
`add_item` and `set_variable` actions. The supply exchange consumes one crystal
and grants exactly one pack once. The permit requires a safe route. Aid-kit use
requires the kit. Quantity/refusal, Lumi/Luma, unknown Vorpax/zhurble, competing
needs and risky-route refusal remain authored comparison cases from the checked-in
prototype. This camp consolidates those cases into one real map; it does not
replace the campaigns or recreate the prototype's four-area ROM.

## Verification

```sh
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy work/venv/bin/python scripts/cloud_game.py pytest tests/custom_game/test_game.py -o addopts=''
```

The finite CLI smoke in `scripts/verify-custom-game-launch.py` checks both the
custom flag and unchanged normal startup. It replaces only the unbounded loop,
then walks to and interacts with the Professor through real input.

The comprehensive acceptance test drives Pygame key-down/key-up events through
the actual client's input manager, event middleware, TMX events, state stack and
renderer. It also injects the engine's controller A event through EventManager
to compare each editor's activation behavior against Return. No position
teleports, direct cursor assignments or mocked conversation states are used in
this journey. The launch helper's initial spawn teleport is normal game startup.
Multiplayer initialization is disabled in this single-player test to avoid
colliding with the independent verifier's server port.

The local HTTP server is labeled **SYNTHETIC HTTP FIXTURE, not live inference** in
its response, model name, screenshots and tests. It proves payloads, follow-up
memory, cancellation, malformed replies, HTTP errors and socket timeout behavior.
It does not prove model quality or real Ollama inference. There is no configured
cloud Ollama service, so live inference remains unverified. Physical controller
hardware has not been tested. There are no hardware writes or ROM builds.

For X11 rendering, install system Xvfb or run the rootless Debian setup:

```sh
bash scripts/setup-custom-game-xvfb.sh
mkdir -p /tmp/.X11-unix
LD_LIBRARY_PATH="$PWD/work/xvfb/usr/lib/x86_64-linux-gnu" work/xvfb/usr/bin/Xvfb :94 -screen 0 1280x720x24 -nolisten tcp &
DISPLAY=:94 SDL_VIDEODRIVER=x11 SDL_AUDIODRIVER=dummy work/venv/bin/python scripts/cloud_game.py pytest tests/custom_game/test_game.py -o addopts=''
```

In managed Codex execution, grant the shell network capability for dependency
fetches, local fixture listeners and Xvfb sockets. This does not require model
credentials. Runtime destinations still follow the managed network policy.

The lockfile was resolved with `uv pip compile --exclude-newer
2026-10-01T00:00:00Z` to retain the repository's seven-day release-age policy on
October 8. Setup uses that exact lock. Update its input file and regenerate with
an appropriate seven-day cutoff when dependencies need an intentional refresh.
Tests regenerate rendered evidence under `work/custom-game-evidence`. Reviewed
captures and test results are retained under this document's evidence directory.


## Upgrade compatibility

The translation compiler invalidates the standard-library gettext cache for the
catalog it rewrites. This prevents cached old item names from surviving an
explicit recompile and failing database validation. The regression test first
loads an old catalog, recompiles it with a new scenario item name, then verifies
the new translation. If you intentionally disable translation recompilation in
an existing desktop config, run the translation preparation step before launching
new source data. The cloud setup already does this in a separate process.
