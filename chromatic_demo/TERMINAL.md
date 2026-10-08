# Mac Text Playground

This Mac terminal demo lets you talk to NPCs through Ollama while comparing nine button-based input methods. The same NPC remembers earlier turns during this session. Chatting never changes quest items or flags. A separate scripted Quest actions menu requires confirmation for each game effect. Offline authored mode remains available for repeatable comparisons. This interface does not execute the ROM or connect to a physical Chromatic.

## Start

From the Tuxemon repository root:

```sh
venv/chromatic/bin/python -m chromatic_demo.terminal --provider ollama --model gemma4:26b-mlx
```

For offline comparisons with predefined replies:

```sh
venv/chromatic/bin/python -m chromatic_demo.terminal --provider authored
```

Double-click `chromatic_demo/Start Text Playground.command` to launch that Ollama configuration in Terminal. The launcher accepts CLI arguments to override it, for example `--provider authored`. Ollama must already be running, and the requested model must be installed. No model is downloaded automatically. Terminal size must be at least 60 columns by 20 rows; 100 by 35 is more comfortable.

Live NPC replies currently require Ollama. ChatGPT retains the earlier optional player-draft helper. For that separate subscription path, explicitly sign in using this project's opt-in account flow:

```sh
venv/chromatic/bin/python -m chromatic_demo.auth login
venv/chromatic/bin/python -m chromatic_demo.auth models
venv/chromatic/bin/python -m chromatic_demo.terminal --provider chatgpt --model ACCOUNT_CATALOG_SLUG
```

Replace `ACCOUNT_CATALOG_SLUG` with a real slug returned for your account. Login consent and account eligibility are required. Configuring a slug does not prove successful inference. This path uses no OpenAI API key or Codex credentials and has no API-billing fallback. See [OpenAI's subscription token-sharing documentation](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference).

## Controls

| Button | Mac key |
| --- | --- |
| D-pad | Arrow keys |
| A | `a`, `A`, or Return on every selectable screen |
| B | `s`, `S`, or Escape outside typing; Escape backs out while typing |
| Start | F1 from any screen |
| Select | Backspace, selects editor actions |
| Quick host keyboard toggle | Tab |
| Exit shortcut | Control-C |

To choose a scenario, press F1, Down, Return. Press Return again on the highlighted scenario to enter its editor. In button mode, Return or `a` chooses the highlighted editor option.

The Start menu contains scenarios, input methods, journal, settings, reset and quit. Every editor offers DEL, PREVIEW, SPELL, CANCEL, GET DRAFT and HOST KEYBOARD. All essential actions have a button route. HOST KEYBOARD is a deliberate unrestricted typing mode: letters including `a` and `s` insert themselves, Backspace deletes, and Return opens preview without sending. Tab switches back while retaining the draft and method. Exit is also available through Start, Quit.

For the quickest conversation, press Tab, type a greeting, then Return to preview it. Press Return again to send it to the selected NPC through Ollama. The reply screen identifies the model. Choose Continue conversation to clear the sent draft and ask a follow-up. Left/Right pages through long replies; Up/Down selects an action. The editor retains the last reply as context.

GET DRAFT is optional help rewriting your outgoing message. It is not required for an NPC reply. In Ollama mode, Send includes the selected NPC's opening, current inventory and flags, available scripted action labels, and the newest complete dialogue pairs that fit within 2048 characters. History is isolated per NPC and described as conversation, not completed game actions. Successful turns append both sides together. Failed, canceled or stale requests append neither side. A provider error or 35-second timeout keeps your draft. PREVIEW lets you retry; Escape/B cancels an active request. No authored text silently substitutes for a failed Ollama reply.

Quest actions (scripted) is optional after an NPC response. Select an authored action and confirm it separately to apply its guarded effect. Model prose cannot award items or change quest flags. Offline authored mode instead sends directly to the existing meaning-and-confirmation flow. ChatGPT mode still offers player drafting with authored quest outcomes; NPC chat is currently Ollama-only.

Player messages allow 1 to 96 printable ASCII characters. NPC prose is bounded to 320 characters. `--ollama-url http://127.0.0.1:PORT` can select another local Ollama-compatible endpoint; both draft assistance and NPC replies use it. Non-loopback addresses are rejected.

Quest state lasts for this process. Changing scenario or input method retains both the draft and earned quest state. Reset requires a separate confirmation and clears every NPC conversation; quitting discards this trial. No scenario grants hidden prerequisites. This is a local trial interface, not a saved-game system or a measured usability study.

## Try These Scenarios

Use Start, Scenarios to select the NPC, then compare methods via Start, Input methods. Use SPELL for missing names, quantities or initials, or Tab for full keyboard input.

| Scenario | What to try | What to check |
| --- | --- | --- |
| Quartermaster | “Exactly one pack, not two.” Then refuse a trade. | Generated wording preserves quantity and negation. Refusal keeps the crystal. One accepted trade spends it; repeating that trade is blocked. |
| Tracker Iona | Correct Luma to Lumi. Ask whether the creature is Vorpax. | Exact names survive drafting; unfamiliar names stay unresolved in authored replies. |
| Medic Ren | Ask to help both companion and scout. Refuse to use the kit. | A competing need or refusal does not silently become a rescue. Choose and confirm the matching meaning. |
| Warden Vale | Accept the flooded shortcut, then refuse the risk. | Acceptance and refusal stay distinct; a permit requires the dry-route flag. |
| Professor | Correct Water to Earth. Ask about the zhurble tactic. | Correct type survives wording; unknown tactic gets clarification. |

For a complete quest, open Quest actions after an NPC reply and choose these actions in order, confirming each one: Quartermaster “Trade for one pack”; Iona “Correct tag name” then “Confirm dry trail”; Ren's scout rescue; Vale “Ask for permit”; Professor “Ask Earth tactics” then “Register entry”. Check Journal for earned flags and remaining items. Trial entry makes the authored gate eligible, but this text adaptation has no walking or gate animation.

## Mechanics And Adaptation Boundaries

| Method | Mechanics retained |
| --- | --- |
| Intent composer | Ask/Offer/Refuse, six NPC topics, Neutral/Cautious/Firm, replace draft with the authored phrase. |
| Keyword chips | Seven NPC-specific chips, prioritizing exact quantities; space-separated append. |
| Initials shorthand | Lowercase word-start prefix matching against six authored utterances. SPELL initials, B back, then select a matching utterance. |
| Predictive grid | Four native character pages and seven authored completion words. This terminal displays a scrolling list: left/right move one cell, up/down move ten. It is not a native grid rendering. |
| Grouped alphabet | Six groups of five characters; choose group then character. B backs out of a group. |
| Custom EdgeWrite | URDL base-four codes: one direction for a–d, two for e–t, three for u through apostrophe. A commits, B erases a direction or opens actions. These are this prototype's custom codes. |
| Dasher inspired tree | Fixed native character order, four-way narrowing. This is selection, not continuous pointer-based Dasher. B restores the root. |
| Radial groups | D-pad selects four petals; A enters a petal, then choose a character. Last petal has nine characters. B returns or opens actions. |
| Host keyboard | Same-Mac text entry, no network pairing. Also reachable from every method with Tab or HOST KEYBOARD. |

The terminal uses actual Python string lengths for native keyboard pages and tree branches. Some C arrays use fixed 30-slot bounds beyond their string length. The adaptation never exposes NUL cells. List edges wrap; grid up/down wraps by ten rather than reproducing the native action-row edge jump. F1 opens the terminal menu from every phase. Return chooses on every selectable screen; each Send and confirmation requires a separate press. B from an editor root opens that menu because this adaptation has no world walking. These layout and navigation differences mean terminal input counts are not native-ROM performance measurements.

## Verification

Run the focused behavior suite from the repository root:

```sh
venv/chromatic/bin/python -m pytest -o addopts='' tests/chromatic_demo/test_terminal.py tests/chromatic_demo/test_providers.py tests/chromatic_demo/test_playground_bridge.py
```

The tests exercise all nine composers, all gesture codes, every tree character, keyboard retention, text rejection, confirmation guards, quest completion, stale requests and synthetic provider responses. Synthetic response fixtures are not evidence of real inference. Real provider and terminal trials should record the actual observed result separately.
The terminal E2E suite launches an independent real curses process in an owned PTY and sends keyboard bytes. It checks decoded screens rather than calling state setters. It covers the Return menu regression, nine entry methods, confirmation and item guards, the complete quest, typing limits, resize, and clean exit:

```sh
venv/chromatic/bin/python -m pytest -o addopts='' tests/chromatic_demo/test_terminal_e2e.py tests/chromatic_demo/test_terminal_disconnect.py -q
```

The default run uses authored mode plus explicitly synthetic loopback HTTP fixtures and skips live model tests. The loopback suite checks real transport, two-turn NPC conversation, request context, separate quest effects, errors, cancellation and long replies. It never replaces the user's Ollama service. To verify real Ollama generation and cancellation against the already installed model:

```sh
OLLAMA_E2E_MODEL=gemma4:26b-mlx venv/chromatic/bin/python -m pytest -o addopts='' tests/chromatic_demo/test_terminal_e2e.py tests/chromatic_demo/test_terminal_disconnect.py -k live_ollama -q
```

Evidence survives each run in `build/chromatic/terminal-e2e/<test>-<unique>/`: `actions.json`, `screen.txt`, and `terminal.raw`. Set `TERMINAL_E2E_EVIDENCE` to change the output root. The tests close only their own processes. Read the [terminal verification map](../.agents/skills/verify/features/terminal.md) for proof boundaries.
