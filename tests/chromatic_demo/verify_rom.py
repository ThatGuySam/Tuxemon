"""Drive the built ROM in PyBoy and record real button-state evidence."""

# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import hashlib
import json
from datetime import datetime, timezone

from pyboy import PyBoy


def verify(build) -> None:
    """Check intent selection, every page, A completion, and B cancel."""
    symbols = {}
    for line in (build / "demo.noi").read_text().splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "DEF":
            symbols[words[1]] = int(words[2], 16)
    provenance = json.loads((build / "provenance.json").read_text())
    evidence = []
    emulator = PyBoy(
        str(build / "demo.gbc"),
        window="null",
        sound_emulated=False,
    )
    emulator.set_emulation_speed(0)

    def state(name):
        return emulator.memory[symbols["_" + name]]

    def button(name):
        emulator.button_press(name)
        emulator.tick(12)
        emulator.button_release(name)
        emulator.tick(12)

    def capture(name):
        path = build / (name + ".png")
        emulator.screen.image.save(path)
        evidence.append(
            {
                "screenshot": path.name,
                "selected": state("selected"),
                "current_page": state("current_page"),
                "in_dialogue": state("in_dialogue"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    try:
        emulator.tick(180)
        assert state("selected") == 0 and state("in_dialogue") == 0
        capture("menu")
        button("up")
        assert state("selected") == 2
        button("down")
        assert state("selected") == 0
        for index, (intent, item) in enumerate(provenance["dialogue"].items()):
            assert state("selected") == index
            button("a")
            assert state("in_dialogue") == 1
            for page in range(len(item["pages"])):
                assert state("current_page") == page
                assert state("in_dialogue") == 1
                capture(f"{intent}-{page}")
                button("a")
            assert state("in_dialogue") == 0
            button("down")
        assert state("selected") == 0
        button("a")
        assert state("in_dialogue") == 1
        button("b")
        assert state("in_dialogue") == 0
        capture("cancelled-menu")
    finally:
        emulator.stop(save=False)
    (build / "emulator-verification.json").write_text(
        json.dumps(
            {
                "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                "rom_sha256": provenance["rom_sha256"],
                "checks": [
                    "up/down wrap",
                    "all three intents",
                    "all dialogue pages",
                    "A completion returns to menu",
                    "B cancels dialogue",
                ],
                "captures": evidence,
                "hardware_verified": False,
            },
            indent=2,
        )
        + "\n"
    )
    print("PyBoy verified all intents, pagination, completion, and cancel.")


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    verify(parser.parse_args().build)
