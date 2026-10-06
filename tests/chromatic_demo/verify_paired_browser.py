#!/usr/bin/env python3
"""Drive a private ROM instance while an actual browser submits paired text."""

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pyboy import PyBoy

if not __debug__:
    raise RuntimeError(
        "Verification requires enabled Python assertions; omit -O"
    )

from chromatic_demo.npc_picker import GLiClassPicker
from chromatic_demo.playground_bridge import Broker, Controller, paired_server

FIXTURE_KEY = "verification-only-local-fixture"


def verify(build: Path, output: Path) -> None:
    """Require the real paired page to produce a reviewed, guarded conversation."""
    output.mkdir(parents=True, exist_ok=False)
    symbols = {}
    for line in (build / "playground.noi").read_text().splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "DEF":
            symbols[words[1]] = int(words[2], 16)
    content = json.loads((build / "playground-provenance.json").read_text())[
        "content"
    ]
    text = content["npcs"][0]["replies"][0]["utterance"]
    picker = GLiClassPicker.from_local_model(
        ROOT / "venv/chromatic-picker-model"
    )
    p = PyBoy(
        str(build / "playground.gbc"), window="null", sound_emulated=False
    )
    controller = None
    server = None
    server_thread = None
    actions = []
    ready = False

    def state(name):
        return p.memory[symbols["_" + name]]

    def tick(frames=1):
        for _ in range(frames):
            p.tick()
            controller.tick()
            if ready:
                assert p.memory[0xFF40] & 0x80, "LCD disabled"
                assert any(
                    lo < 100
                    for lo, _ in p.screen.image.convert("RGB").getextrema()
                ), "Blank LCD"

    def button(key):
        p.button_press(key)
        tick(2)
        p.button_release(key)
        tick(20)
        actions.append(
            {"key": key, "phase": state("phase"), "method": state("ui_id")}
        )
        (output / "actions.json").write_text(
            json.dumps(actions, indent=2) + "\n"
        )

    try:
        p.set_emulation_speed(0)
        controller = Controller(p, Broker(content, picker))
        tick(180)
        ready = True
        button("up")
        button("a")
        assert state("npc_id") == 0
        while state("phase") == 6:
            button("a")
        assert state("phase") == 2
        button("start")
        for _ in range(8):
            button("down")
        button("a")
        assert state("ui_id") == 8 and state("phase") == 2
        button("a")
        assert state("phase") == 4
        server = paired_server(controller, FIXTURE_KEY)
        server_thread = threading.Thread(
            target=server.serve_forever, daemon=True
        )
        server_thread.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        (output / "ready.json").write_text(
            json.dumps(
                {
                    "url": url,
                    "fixture_key": FIXTURE_KEY,
                    "fixture_text": text,
                    "credential_scope": "synthetic owned verification instance only",
                },
                indent=2,
            )
            + "\n"
        )
        print(
            json.dumps({"url": url, "ready": True, "fixture_text": text}),
            flush=True,
        )
        deadline = time.monotonic() + 55
        while state("phase") == 4 and time.monotonic() < deadline:
            tick()
            time.sleep(1 / 60)
        assert state("phase") == 3, "Browser did not deliver paired preview"
        draft = bytes(
            p.memory[
                symbols["_draft"] : symbols["_draft"] + state("draft_length")
            ]
        ).decode("ascii")
        assert draft == text
        assert state("draft_source") == 3 and state("committed_count") == 0
        assert state("quest_flags") == 0 and state("inventory") == 3
        tick(30)
        p.screen.image.save(output / "paired-preview.png")
        button("a")
        deadline = time.monotonic() + 14
        while state("phase") == 4 and time.monotonic() < deadline:
            tick()
            time.sleep(1 / 60)
        assert state("phase") == 5 and state("source") == 1
        assert state("quest_flags") == 0 and state("inventory") == 3
        result = controller.last_result
        assert result is not None and result.model_id and result.model_revision
        tick(30)
        p.screen.image.save(output / "paired-meaning.png")
        if state("outcome_id") != 0:
            button("down")
            button("a")
            tick(30)
            button("a")
            tick(30)
        button("a")
        assert state("phase") == 6 and state("quest_flags") == 32
        tick(30)
        p.screen.image.save(output / "paired-reply.png")
        report = {
            "status": "passed",
            "rom_sha256": hashlib.sha256(
                (build / "playground.gbc").read_bytes()
            ).hexdigest(),
            "browser_input_expected": True,
            "literal_text": draft,
            "source": 3,
            "explicit_send_count": state("committed_count"),
            "flags_after_confirmation": state("quest_flags"),
            "inventory": state("inventory"),
            "real_picker_result": asdict(result),
            "actions": actions,
            "user_sessions_touched": False,
        }
        (output / "result.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(
            "Paired browser input and real-model conversation verified.",
            flush=True,
        )
    except Exception as error:
        p.screen.image.save(output / "failure.png")
        snapshot = {
            name: state(name)
            for name in (
                "phase",
                "cursor",
                "outcome_id",
                "quest_flags",
                "inventory",
                "npc_id",
                "player_x",
                "player_y",
            )
        }
        (output / "failure.json").write_text(
            json.dumps(
                {"error": str(error), "state": snapshot, "actions": actions},
                indent=2,
            )
            + "\n"
        )
        raise
    finally:
        if server:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)
        if controller:
            controller.close()
        p.stop(save=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    verify(args.build.resolve(strict=True), args.output_dir.resolve())
