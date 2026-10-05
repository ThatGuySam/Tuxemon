# Conversation Playground

The Last Ascent is a walkable, authored late-game story with four areas, five NPCs, and 30 dialogue outcomes. It lets you compare nine conversation interfaces in the same quest state. It is original game fiction, not canonical Tuxemon endgame. Rockitten's Earth type comes from the fork's English translation source. New locations, characters, duties, and dialogue are authored fiction.

The playable areas are Summit Camp, Supply Terrace, Echo Ravine, and Crown Approach. Walk east or west through their boundary paths to move between them. The Professor prepares your tactics; the Quartermaster trades supplies; Tracker Iona checks a rare creature clue; Medic Ren handles an injured scout; Warden Vale controls trial entry.

## Start the Local Bridge

From the Tuxemon repository root, use the installed environment and model snapshot:

```sh
venv/chromatic-picker/bin/python -m chromatic_demo.playground_bridge \
  --rom build/chromatic/playground/playground.gbc \
  --content chromatic_demo/worlds/last_ascent.json \
  --picker-model venv/chromatic-picker-model \
  --provider ollama --model gemma4:26b-mlx --window SDL2
```

This starts an owned PyBoy instance. Ollama composes the player's outgoing drafts; the GLiClass picker suggests an authored NPC outcome. NPC response prose and quest effects remain authored. The bridge is for this emulator instance. It cannot attach to another emulator or the physical Chromatic's RAM.

The ninth interface needs the owned bridge plus its paired entry server. Create a private directory with `mkdir -m 700 -p /private/tmp/last-ascent-session`, then add `--pairing-file /private/tmp/last-ascent-session/pairing.secret` to enable that server. The program creates or reads a private pairing key outside the repository and prints the actual local endpoint. Open its origin URL, ending in `/`, for the Mac text-entry page. Enter the pairing key privately. Select Paired host and Receive host text in the game before queuing a draft. Queuing does not send the message to the NPC. The game still requires preview and confirmation.

The server defaults to loopback on an automatically selected port. Nonloopback binding requires a TLS certificate and key. Phone/LAN access needs separate configuration and verification. The experimental handheld Wi-Fi firmware remains uninstalled. Neither the paired page nor this command establishes live model communication on physical hardware.

## Controls and Interface Ranking

The Mac SDL2 window uses arrow keys for the D-pad, `a` for A, `s` for B, Return for Start, and Backspace for Select. Press Escape to close your game. These mappings come from the installed PyBoy SDL2 plugin.

The menu's ranking is a design judgment, not a measured typing-speed result. Press Start to open the conversation menu. Choose an interface with Up/Down and A; B or Start resumes. The menu also offers Journal / inventory and Reset test world. Switching interfaces preserves an unsent draft for the same NPC.

In the world, the D-pad walks and A talks near an NPC. A advances opening and reply pages; B returns to the world. Read the opening, then press A after its final page to enter the selected composer.

| Rank | Interface | Actual Controls and Behavior |
|---|---|---|
| 1 | Keyword chips | Move focus and press A to append a chip. NPC-specific chips include topic words and negation. Use Spell for words outside the chips. |
| 2 | Intent composer | Select Ask, Offer, or Refuse; choose a topic; then choose Neutral, Cautious, or Firm. The composer creates an authored draft for review. |
| 3 | Initials shorthand | Use Spell to enter word initials. Matching authored utterances become selectable expansions. GET DRAFT can ask Ollama to expand a mixed initials/keyword draft. |
| 4 | Predictive grid | Navigate a stable character grid and press A for a character. PAGE switches letter, case, number, and punctuation pages. Complete uses a small authored word list. |
| 5 | Grouped alphabet | Choose a five-character group, then a character. B returns to group selection. Spell provides the full character grid. |
| 6 | Custom EdgeWrite | Enter one to three directions, then A commits the character shown in the on-screen trace legend. B erases a trace step; with an empty trace, B enters the actions. This is a custom direction-code experiment, not the original EdgeWrite alphabet. |
| 7 | Dasher inspired | Select progressively narrower character groups with A. B resets the branch selection. Characters use a fixed authored frequency order; there is no continuous zooming or learned probability model. |
| 8 | Radial groups | Up chooses A-G, Right H-N, Down O-U, and Left the remaining group. A opens the group; select a character and press A. B returns to petals. |
| 9 | Paired host | Select Receive host text, then queue up to 96 printable ASCII characters in the authenticated Mac page. Requires the owned PyBoy bridge and paired server. Spell remains available offline. |

The editor exposes DEL, PREVIEW, SPELL, CANCEL, and GET DRAFT. DEL removes a character. SPELL opens the exact character grid. CANCEL returns to the world. GET DRAFT requests optional player-side wording when a host is available; offline it previews the existing draft. Review every generated draft for names, negation, quantities, and commitments.

PREVIEW shows the exact outgoing text and its source. Focus SEND THIS TEXT and press A to submit it. Reaching the preview does not submit. After submission, CONFIRM THE MEANING shows the proposed outcome. Choose YES, THAT MEANING to apply it, CHOOSE MEANING to select an authored outcome yourself, or EDIT TEXT to revise. Until confirmation, the game awards nothing. Failed item or quest guards retain your words.

The draft limit is 96 printable ASCII characters. At the limit the editor asks you to delete first. The paired page rejects non-ASCII text, empty text, and overlong input. Host requests can time out or be cancelled with B while preserving the draft. The bridge checks request, draft, and context versions before accepting a response.

## Complete the Quest

Use the exact authored utterances from `worlds/last_ascent.json`, or write your own message and explicitly select its intended meaning. These are authored game instructions, not examples of generated model output.

1. At Summit Camp, ask the Professor for Earth tactics. Confirm `earth_plan` to prepare your tactics notes.
2. At Supply Terrace, trade exactly one crystal for one pack. Confirm `buy_one`. This consumes the crystal and adds the supply pack.
3. In Echo Ravine, correct Iona's tag from Luma to Lumi with `correct_name`. Then confirm `safe_route` to mark the dry passage.
4. Find Ren in the same ravine. Confirm `rescue_scout` to use the aid kit and escort the injured scout to camp.
5. At Crown Approach, give Vale the route report and confirm `get_permit`.
6. Return to the Professor and confirm `epilogue`. The complete duties register your trial entry and unlock the gate tile at Crown Approach.

You start with an aid kit and a crystal. A completed route leaves a permit and supply pack. Quest flags and item bits appear in the journal. This prototype keeps progress in session RAM; quitting or Reset test world clears it. It has no durable save system, battle simulation, or playable championship combat.

## Try Realistic Conversation Stress Routes

Reset between comparisons so the same guards and items apply. Try each route in more than one interface and inspect the proposed meaning before confirmation.

- At the Quartermaster, request two packs, decline the trade, then ask for exactly one. Verify that refusal leaves the crystal untouched, the valid trade consumes it, and a second request does not duplicate supplies.
- At Iona, correct Luma to Lumi, ask about the unfamiliar name Vorpax, then say you do not want to chase Lumi. The correction, unknown-name question, and refusal have separate outcomes. Continue with the dry route when ready.
- At Ren, explain that both the scout and your companion need help. Refuse kit use until ready, then escort the scout. Check the journal before and after confirmation to distinguish discussion from consumption.
- At Vale, ask to accept the flooded shortcut's risk, then explicitly refuse the shortcut. Compare the suggested meanings. The flooded cut remains closed; use the route report and permit progression.
- At the Professor, correct the claim that Rockitten is Water-type. Try an unfamiliar tactic name, then ask for a safe preparation plan. Neither an unknown noun nor a type correction should silently become trial registration.

## Classifier Evidence and Limits

The local picker uses the GLiNER-family GLiClass classifier, pinned as `knowledgator/gliclass-edge-v3.0`. It scores concise action descriptions for the current NPC. These scores are uncalibrated. The current policy accepts a suggestion only when the leading score reaches 0.80 and exceeds the runner-up by at least 0.03; otherwise it abstains. Those gates are policy values, not demonstrated probabilities of correctness.

The [canonical world probe](../build/chromatic/playground/picker-world-probe.json), recorded October 5, 2026 at 21:41:46 UTC, matched 6 of 25 expected authored labels. It used the current world's `classifier_label` descriptions and all six outcomes per NPC, matching the runtime bridge. This is a local fixture check, not a benchmark or a gameplay usability study. It supports keeping the picker advisory. Always confirm the meaning, especially for negation, unknown names, and quantities. Offline keyword matching is also advisory and can choose an overlapping keyword; CHOOSE MEANING is the recovery path.

This guide describes the inspected implementation in `playground.py`, `playground_bridge.py`, `native/playground.c`, `npc_picker.py`, and `worlds/last_ascent.json`. The [native emulator report](../build/chromatic/playground/playground-verification.json) and [build verification](../build/chromatic/playground/playground-build-verification.json) record their own checks. Physical playback, handheld controls, radio transport, and firmware installation require their own evidence.

## Rebuild and Verify

The installed GBDK build uses the original Python environment. The live verifier uses the separately pinned classifier environment. Run from the repository root.

```sh
venv/chromatic/bin/python -m chromatic_demo.playground --repo . --content chromatic_demo/worlds/last_ascent.json --output build/chromatic/playground
venv/chromatic/bin/python tests/chromatic_demo/verify_playground.py build/chromatic/playground
venv/chromatic/bin/python tests/chromatic_demo/verify_playground_build.py build/chromatic/playground
venv/chromatic-picker/bin/python tests/chromatic_demo/verify_live_bridge.py
```

The live verifier performs real local inference and writes actual receipts under `build/chromatic/playground/live-evidence`. It needs the installed pinned model and Ollama model. [Verification setup](VERIFY.md) and the local ranked interface frames retain what was actually checked.

The movement renderer was corrected after the initial demo. The local movement verification record records the current ROM and frame-by-frame checks. Run `venv/chromatic/bin/python tests/chromatic_demo/verify_movement_frames.py build/chromatic/playground` to repeat them.

The shared renderer now also preserves menu and editor content. The local screen verification record records the latest ROM. Repeat its check with `venv/chromatic/bin/python tests/chromatic_demo/verify_screen_frames.py build/chromatic/playground`. Existing running windows keep their original loaded ROM until replaced by a new game process.
