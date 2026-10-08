# Tuxemon Chromatic Prototype

The new walkable conversation playground is described in [PLAYGROUND.md](PLAYGROUND.md). It adds four areas, five NPCs, guarded quests, inventory, and nine text-entry approaches. The instructions below retain the earlier three-choice snapshot prototype.

This prototype turns a small part of Sam's Tuxemon fork into a playable Game Boy Color dialogue scene. It uses the Professor and Rockitten sprites, three conversation choices, real English translation entries, and optionally generated replies from ChatGPT plan usage or local Ollama. Generated dialogue is a precompiled snapshot. The ROM has no runtime network connection.

The fork baseline is `9e6258ff726b786040a267e8bdbbf037b560285e`, on `development` from https://github.com/ThatGuySam/Tuxemon. Existing Tuxemon gameplay code is unchanged. This is a separate small port, with no combat, movement, inventory, or quests.

## Run the Prototype

From `/Users/athena/Code/Tuxemon`:

```sh
uv venv venv/chromatic --python python3
uv pip install --python venv/chromatic/bin/python --exclude-newer '2026-09-28T00:00:00Z' -r chromatic_demo/requirements-dev.txt
venv/chromatic/bin/python -m chromatic_demo.rom --repo . --output build/chromatic/offline
venv/chromatic/bin/python tests/chromatic_demo/verify_rom.py build/chromatic/offline
```

The dependency cutoff preserves the workspace's seven-day release-age policy for this October 5 setup. For later installs, retain an equivalent minimum age. The installed compiler default is the ModRetro plugin's GBDK at `~/Library/Application Support/modretro-chromatic/toolchain/.local/gbdk/bin/lcc`. Set `GBDK_LCC` or pass `--compiler` for another compiler.

Use Up or Down to select an intent. Press A to talk or advance a page. Press B to return to the choices. The screen is 160 by 144 pixels.

Generate a fresh local model snapshot:

```sh
venv/chromatic/bin/python -m chromatic_demo.rom --repo . --output build/chromatic/ollama --provider ollama --model gemma4:26b-mlx
```

The Ollama provider accepts only loopback addresses, an explicit model, and completed inference. It limits output to 320 printable ASCII characters. An unavailable provider stops generation. The separate offline build remains playable without any model. A JSON import uses the `IMPORTED SNAPSHOT` label and records its file hash. It cannot claim a measured model result.

Each build writes `demo.gbc`, generated C and tile data, `provenance.json`, and compiler symbols. Provenance records the real replies, prompts, provider, timestamps, source hashes, asset transformations, compiler command, and ROM digest.

## Connect ChatGPT Plan Usage

```sh
venv/chromatic/bin/python -m chromatic_demo.auth login --no-browser
venv/chromatic/bin/python -m chromatic_demo.auth status
venv/chromatic/bin/python -m chromatic_demo.auth models
venv/chromatic/bin/python -m chromatic_demo.rom --repo . --output build/chromatic/chatgpt --provider chatgpt --model SELECTED_CATALOG_SLUG
venv/chromatic/bin/python -m chromatic_demo.auth logout
```

`SELECTED_CATALOG_SLUG` is an explicit placeholder. Replace it with a model returned by the signed-in account's catalog. Login prints a short-lived authorization URL and listens on a local loopback callback for up to three minutes. Open it in Chrome or your own browser and review the requested grant. Agent Firefox work must use a dedicated new window.

The companion uses the documented public Sign in with ChatGPT flow with PKCE, state, nonce, JWT signature validation, refresh, and granted-scope checks. Credentials live outside source under `~/.local/share/tuxemon-chromatic-auth`, with owner-only access and atomic writes. The prototype retains one account registration. Logout clears tokens and attempts revocation; unsuccessful revocation is reported. No API key or separately billed API fallback is configured.

Model requests use the public Responses endpoint, `store: false`, and `stream: true`. They require a completed response before accepting text. Socket timeouts and stream budgets bound normal failures, but do not establish a guaranteed hard cancellation deadline. Generated prose does not change game state. Model factual accuracy and suitability still require human review.

Official references: [registration](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions), [inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference).

## Verify and Try USB Playback

```sh
venv/chromatic/bin/python -m pytest -o addopts= -q tests/chromatic_demo
venv/chromatic/bin/ruff check chromatic_demo tests/chromatic_demo
venv/chromatic/bin/python tests/chromatic_demo/verify_rom.py build/chromatic/ollama
```

The verification script boots the exact compiled ROM in PyBoy, drives all intents and pages, and records screenshots and state evidence. Emulator success does not establish physical playback.

The USB runner uses the plugin's public MCP client with an explicit workspace. It inspects the exact ROM, discovers the selected player, and streams a timed host-emulated demo. The following command uses the installed plugin directory verified in this run:

```sh
venv/chromatic/bin/python -m chromatic_demo.usb \
  --plugin /Users/athena/.codex/plugins/cache/openai-curated-remote/modretro-chromatic/1.0.33+codex.distribution.66e8961d3ce30093ea3c9ee4 \
  --repo . --rom build/chromatic/ollama/demo.gbc \
  --player 1 --seconds 90
```

This changes the display temporarily through USB host emulation. It does not flash a cartridge or MCU, and it disables save loading and writing. The runner preserves the original operation journal and does not retry an uncertain action. The ROM maps Up, Down, A, and B. Forwarding of the physical USB controls awaits Sam's check.

## Paired Companion Endpoint

The future MCU client uses `POST /v1/dialogue`, a bearer pairing secret, and JSON with exactly `request_id` and `intent`. The server accepts only the three game intents. A reply echoes the request ID, bounds text to 320 printable ASCII characters, and labels generated versus authored fallback text. Account tokens stay on the Mac.

```sh
venv/chromatic/bin/python -m chromatic_demo.server --provider ollama --model gemma4:26b-mlx
```

This starts a loopback listener and prints its actual local port. Stop it with Ctrl-C after testing. The private pairing file is `~/.local/share/tuxemon-chromatic-network/pairing.secret`; the server creates it with owner-only access and does not print it. A nonloopback bind requires `--tls-cert` and `--tls-key`. The handheld must trust the configured CA and validate the certificate hostname. LAN operation has not been tested.

A real paired loopback request returned completed Ollama dialogue. HTTP/TLS tests use clearly synthetic credentials and certificates. These checks establish the companion protocol, not Wi-Fi operation on the handheld.

## Hardware Work Remaining

An optional ESP32 dialogue client is now implemented and compiled, using the existing firmware display, buttons, Wi-Fi, and a certificate-validated HTTPS companion call. [firmware/README.md](firmware/README.md) records the reviewed patch, successful builds, and installation boundary. Firmware source and toolchain are saved under the ignored `venv/chromatic-firmware/` directory.

The enabled client exceeds the stock 1 MiB app partition. Its separate 2 MiB build profile changes the application layout and is not approved for device installation. The stock layout is untouched. No firmware was flashed, so direct radio and live handheld-to-model dialogue remain untested. The actual installed layout and recovery need a separate review before any physical write.

The experimental enabled firmware deliberately keeps the MCU awake, including while its panel and radio are off. Wi-Fi configuration lives only in RAM and must be supplied again after reboot. These prototype exceptions preserve the stock configuration and avoid unencrypted credential persistence. Battery behavior and on-device private provisioning remain unverified. The cartridge-to-ESP32 mailbox and iPhone setup portal remain unimplemented. [HARDWARE.md](HARDWARE.md) preserves the initial source findings; the firmware guide supersedes its initial toolchain/build status.

Python matches the source project and is sufficient for this companion and asset conversion. The small C renderer uses the existing GBDK ABI. No new Rust runtime or firmware rewrite is needed for this initial milestone.

## Licenses and Attribution

New code is GPL-3.0-or-later, matching Tuxemon's contribution terms. Professor overland art is by Kurt Stine. Rockitten overland art is by tamashihoshi. Both use [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), as recorded in the fork's `ATTRIBUTIONS.md`. This prototype crops the front idle frames and converts them to four grayscale levels and Game Boy tiles. Preserve these credits and the source when sharing the derivative ROM.

## Delivery State

Local prototype only. No task branch, commit, push, PR, cartridge write, firmware update, or publication was performed. See `verification/RESULTS.md` for this run's observed results and remaining gaps.
