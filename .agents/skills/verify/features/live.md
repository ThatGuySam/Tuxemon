# Live Companion

The owned Mac emulator accepts authenticated paired text and real local model suggestions while retaining player review before effects.

## Sub-features

- GLiClass interpretation with real score/model provenance.
- Paired HTTP text entering exact Preview without Send.
- Completed local Ollama outgoing draft or an explicitly reported provider failure.
- Missing-picker authored fallback with unchanged quest and inventory before confirmation.

## How to get to it (user POV)

The documented Mac bridge starts the ROM with the pinned picker and optional Ollama. Choose Paired host and Receive, then queue text from the paired page. GET DRAFT asks for outgoing wording. Send reaches meaning confirmation.

## Driving it with PyBoy and HTTP

Preconditions: `venv/chromatic-picker`, `venv/chromatic-picker-model`, and local Ollama with `gemma4:26b-mlx` when generation is being proved. Fresh bundle and passing doctor.

- Run `.agents/skills/verify/scripts/control.py drive --run "$VERIFY_RUN" --feature live`.
- Require real model identity/scores for classification, actual HTTP 202 with exact resulting Preview, explicit source labels, and unchanged inventory/quest flags before meaning confirmation.
- Inspect `compose_completed` in the receipt. A preserved-draft provider failure verifies failure handling; it does not establish successful generation.
- Loopback servers and secrets are created only for this run and torn down in its own finally blocks.

## Gotchas

No ChatGPT sign-in, account token, paid API, LAN exposure, or physical USB action is required. Scores are uncalibrated and the picker remains advisory. This route proves the owned emulator integration; it cannot establish handheld radio or a vendor-stream RAM hook.
