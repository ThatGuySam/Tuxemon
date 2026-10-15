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

The adapter calls `/api/chat` with distinct system/NPC and player roles and
disables thinking so local models produce the requested NPC answer directly. It makes
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
8192 characters and 64 KiB HTTP payloads. Requests have a 60-second deadline and
socket timeout. The deadline is checked between reads; a blocked read can take
one further socket-timeout interval to finish. Cancellation invalidates the request immediately; the bounded
network operation finishes in a daemon worker. Late results cannot overwrite a
new draft or NPC conversation. A second worker is not launched while a cancelled
request is still finishing, including after closing and reopening the overlay.

Each NPC retains its own draft, input method and up to 20 successful conversation
turns in the selected local custom profile. Follow-up prompts include bounded recent history and current
authored quest facts. Completed turns and drafts survive restart. Pending requests never resume or resend.
Start > Reset story explicitly clears story flags, scenario items, every NPC's
history, methods and drafts in the selected profile. It is repeatable and leaves other profiles and campaign data alone. If saving is
disabled, reset clears only the current session and explicitly retains the saved file.

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

## Verified Mac launch

On macOS, use the same Python 3.12 setup and the installed local model:

```sh
export TUXEMON_OLLAMA_URL=http://127.0.0.1:11434
export TUXEMON_OLLAMA_MODEL=gemma4:26b-mlx
SDL_VIDEODRIVER=cocoa work/venv/bin/python scripts/cloud_game.py scripts/play-custom-game.py
```

`play-custom-game.py` launches the existing game with the custom scenario and
multiplayer initialization disabled. It avoids the engine's default multiplayer
port for this single-player demo. The storage wrapper keeps config and saves
under this checkout's `work/userdata`.

Run the real-model verification separately from the synthetic tests:

```sh
SDL_VIDEODRIVER=cocoa SDL_AUDIODRIVER=dummy work/venv/bin/python scripts/cloud_game.py scripts/verify-custom-game-live.py
```

This command opens a finite native window, walks to the Professor, selects a word
with Return, switches to keyboard, previews and sends the exact message, and
checks a real Ollama reply and name recall. It records screenshots and JSON under
`work/live-evidence`. It sends requests to the explicitly configured model and
does not download models. Failures return a nonzero exit status.

The deterministic actual-game acceptance test runs in a child process so its
loaded database, display scale and imported renderer state cannot leak into
other tests. Its synthetic HTTP responses remain explicitly labeled.


## Persistent custom profiles

The launcher uses the `default` custom profile. Set `TUXEMON_CUSTOM_PROFILE` before
launch to choose another profile, such as `cedar`. Names use 1-32 lowercase letters,
digits, hyphens or underscores. These profiles are separate from campaign save slots.

```sh
TUXEMON_CUSTOM_PROFILE=cedar SDL_VIDEODRIVER=cocoa work/venv/bin/python scripts/cloud_game.py scripts/play-custom-game.py
```

Snapshots live under `work/userdata/saves/custom-last-ascent/<profile>.json` when
using the repository storage wrapper. `TUXEMON_USERDATA` can select another storage
root for isolated verification. The game autosaves valid draft edits, input-method
changes and accepted completed replies. Stable authored NPC IDs preserve ownership.
Restart returns to the camp and editing mode. It does not restore quest state,
position, a waiting request, cursor, keyboard mode or editor gestures in progress.
Loading a campaign slot detaches the custom profile and clears the custom runtime.

The JSON format has an explicit schema and version. Writes use a unique adjacent
temporary file, fsync and atomic replacement. A process lock prevents simultaneous
writers to the same profile. Missing files start empty. Invalid, oversized, truncated,
wrong-profile or unsupported-version files remain untouched. The game starts an
empty session and visibly disables saving for that profile. It never silently
substitutes another profile or downgrades an unknown version. Close the game and
move the damaged file aside, or choose a new profile, to resume saving.

Conversation files contain plain text, including player messages and NPC replies.
On macOS, new save files and temporary files are owner-readable/writable only.
There is no application cloud sync or encryption. Send still transmits the draft,
authored facts and bounded recent history to the configured Ollama endpoint.
Reset story clears the current valid profile's conversations. To delete the file,
close all games using the profile and remove its JSON and any matching hidden
`.<profile>-*.tmp` files left by an interrupted write. The empty `.lock` file holds
no conversation text. This is ordinary deletion, not secure erasure.

Run native restart verification with an unused evidence directory:

```sh
TUXEMON_OLLAMA_URL=http://127.0.0.1:11434 TUXEMON_OLLAMA_MODEL=gemma4:26b-mlx SDL_VIDEODRIVER=cocoa SDL_AUDIODRIVER=dummy work/venv/bin/python scripts/cloud_game.py scripts/verify-custom-game-persistence.py --live --output work/persistence-check
```

The command uses separate test profiles and nine sequential game processes. It makes
two real model calls and uses a labeled synthetic fixture for quitting with a pending
request. It checks exact drafts, methods, history, NPC/profile isolation, reset,
damaged/future files and no automatic resend. The Windows lock backend is implemented
with `msvcrt.locking`; Windows runtime verification remains outstanding.
