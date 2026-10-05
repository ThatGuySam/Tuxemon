"""Verify actual LCD frames preserve the world background during movement."""

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pyboy import PyBoy


def verify(build: Path) -> None:
    symbols = {}
    for line in (build / "playground.noi").read_text().splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "DEF":
            symbols[words[1]] = int(words[2], 16)
    captures = []
    content = json.loads((build / "playground-provenance.json").read_text())[
        "content"
    ]
    directory = build / "movement-after"
    directory.mkdir(exist_ok=True)

    def trace(name, key, hold_frames, frames):
        emulator = PyBoy(
            str(build / "playground.gbc"), window="null", sound_emulated=False
        )
        try:
            emulator.set_emulation_speed(0)
            emulator.tick(180)
            if name == "blocked":
                companion = content["npcs"][0]
                target = (companion["x"] + 3, companion["y"] + 4)
                for field, desired, negative, positive in (
                    ("player_x", target[0], "left", "right"),
                    ("player_y", target[1], "up", "down"),
                ):
                    for _ in range(20):
                        actual = emulator.memory[symbols["_" + field]]
                        if actual == desired:
                            break
                        direction = negative if actual > desired else positive
                        emulator.button_press(direction)
                        emulator.tick(2)
                        emulator.button_release(direction)
                        emulator.tick(20)
                    assert emulator.memory[symbols["_" + field]] == desired
            baseline = bytes(
                emulator.memory[0x9800 + y * 32 + x]
                for y in range(16)
                for x in range(20)
            )
            hint_encoding = {
                char: emulator.memory[0x9800 + 16 * 32 + column]
                for column, char in enumerate("DPAD WALK START MENU")
            }
            start = (
                emulator.memory[symbols["_player_x"]],
                emulator.memory[symbols["_player_y"]],
            )
            evidence = []
            emulator.button_press(key)
            for frame in range(1, frames + 1):
                emulator.tick(1)
                if frame == hold_frames:
                    emulator.button_release(key)
                tiles = bytes(
                    emulator.memory[0x9800 + y * 32 + x]
                    for y in range(16)
                    for x in range(20)
                )
                dark = sum(
                    min(rgb) < 100
                    for rgb in emulator.screen.image.convert(
                        "RGB"
                    ).get_flattened_data()
                )
                position = (
                    emulator.memory[symbols["_player_x"]],
                    emulator.memory[symbols["_player_y"]],
                )
                assert tiles == baseline, (
                    name,
                    frame,
                    "background was rewritten",
                )
                assert emulator.memory[0xFF40] & 0x82 == 0x82, (
                    name,
                    frame,
                    "LCD or sprites disabled",
                )
                assert dark > 0, (name, frame, "all-white frame")
                path = directory / f"{name}-{frame:02}.png"
                emulator.screen.image.save(path)
                evidence.append(
                    {
                        "frame": frame,
                        "position": position,
                        "dark_pixels": dark,
                        "background_sha256": hashlib.sha256(tiles).hexdigest(),
                        "screenshot": path.name,
                        "screenshot_sha256": hashlib.sha256(
                            path.read_bytes()
                        ).hexdigest(),
                    }
                )
            if name == "blocked":
                assert position == start
            elif name == "step":
                assert position == (start[0], start[1] + 1)
            elif name == "hint":
                assert position == (start[0], start[1] - 1)
                assert bytes(
                    emulator.memory[0x9800 + 16 * 32 + column]
                    for column in range(20)
                ) == bytes(
                    hint_encoding[char] for char in "A TALK  START MENU  "
                )
            else:
                assert position[1] > start[1] + 1
            assert emulator.memory[0xFE00] == (position[1] + 2) * 8 + 16
            assert emulator.memory[0xFE01] == position[0] * 8 + 8
        finally:
            emulator.stop(save=False)
        captures.append({"name": name, "start": start, "frames": evidence})

    trace("step", "down", 2, 24)
    trace("blocked", "up", 2, 24)
    trace("held", "down", 25, 32)
    trace("hint", "up", 2, 24)
    report = {
        "rom_sha256": hashlib.sha256(
            (build / "playground.gbc").read_bytes()
        ).hexdigest(),
        "hardware_verified": False,
        "checks": [
            "world background tilemap unchanged in every sampled movement frame",
            "LCD and sprites remain enabled",
            "no all-white frame",
            "single-step and blocked collision behavior",
            "held repeat continues without background clearing",
        ],
        "traces": captures,
    }
    before = build / "movement-before"
    if (before / "frames.json").exists() and (
        before / "playground.gbc"
    ).exists():
        frames = json.loads((before / "frames.json").read_text())
        report["observed_before"] = {
            "rom_sha256": hashlib.sha256(
                (before / "playground.gbc").read_bytes()
            ).hexdigest(),
            "min_terrain_tiles": min(
                frame["terrain_tiles"] for frame in frames
            ),
            "min_dark_pixels": min(frame["dark_pixels"] for frame in frames),
            "sprite_disabled_frames": [
                frame["frame"]
                for frame in frames
                if not frame["sprite_enabled"]
            ],
            "trace": "movement-before/frames.json",
        }
    (build / "movement-frame-verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(
        "Movement verified frame-by-frame without world clearing or white frames."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    verify(parser.parse_args().build)
