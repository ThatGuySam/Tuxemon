"""Exercise the built playground through real PyBoy buttons and record evidence."""

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from pyboy import PyBoy


def verify(build: Path) -> None:
    symbols = {}
    for line in (build / "playground.noi").read_text().splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "DEF":
            symbols[words[1]] = int(words[2], 16)
    provenance = json.loads((build / "playground-provenance.json").read_text())
    content = provenance["content"]
    captures = []
    events = []
    keyboard_page = 0
    keyboard_declaration = next(
        line
        for line in (build / "playground.c").read_text().splitlines()
        if "keyboard_sets[4]" in line
    )
    keyboard_sets = [
        ast.literal_eval(value)
        for value in re.findall(r'"(?:\\.|[^"\\])*"', keyboard_declaration)
    ]

    def state(name):
        return p.memory[symbols["_" + name]]

    def text():
        if not state("draft_length"):
            return ""
        return bytes(
            p.memory[
                symbols["_draft"] : symbols["_draft"] + state("draft_length")
            ]
        ).decode("ascii")

    def button(name):
        nonlocal keyboard_page
        if (
            name == "a"
            and state("phase") == 2
            and (state("ui_id") == 3 or state("spelling"))
            and state("cursor") == 31
        ):
            keyboard_page = (keyboard_page + 1) % 4
        p.button_press(name)
        p.tick(3)
        p.button_release(name)
        p.tick(20)
        events.append(name)

    def capture(name):
        path = build / f"verify-{name}.png"
        p.screen.image.save(path)
        captures.append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "state": {
                    n: state(n)
                    for n in (
                        "phase",
                        "ui_id",
                        "area",
                        "player_x",
                        "player_y",
                        "npc_id",
                        "draft_length",
                        "quest_flags",
                        "inventory",
                        "committed_count",
                        "source",
                    )
                },
            }
        )

    def focus(index):
        if state("phase") == 2 and (state("ui_id") == 3 or state("spelling")):
            queue = deque([(state("cursor"), [])])
            seen = set()
            while queue:
                cursor, route = queue.popleft()
                if cursor == index:
                    for direction in route:
                        button(direction)
                    assert state("cursor") == index
                    return
                if cursor in seen:
                    continue
                seen.add(cursor)
                for direction, destination in (
                    ("right", (cursor + 1) % 37),
                    ("left", (cursor - 1) % 37),
                    ("up", cursor - 10 if cursor >= 10 else 36),
                    ("down", cursor + 10 if cursor + 10 < 37 else 32),
                ):
                    queue.append((destination, route + [direction]))
        for _ in range(100):
            if state("cursor") == index:
                return
            button("right")
        raise AssertionError(("focus unreachable", index, state("cursor")))

    def mode(method):
        old = text()
        button("start")
        rank = [1, 0, 2, 3, 4, 5, 6, 7, 8].index(method)
        while state("cursor") != rank:
            button("down")
        button("a")
        assert state("ui_id") == method and text() == old

    def finish_opening():
        for _ in range(8):
            if state("phase") != 6:
                break
            button("a")
        assert state("phase") == 2

    def clear_draft():
        mode(3)
        focus(32)
        while state("draft_length"):
            button("a")

    def type_literal(message):
        for char in message:
            page, index = next(
                (page, chars.index(char))
                for page, chars in enumerate(keyboard_sets)
                if char in chars
            )
            while keyboard_page != page:
                focus(31)
                button("a")
            focus(index)
            button("a")
        assert text() == message

    def preview(method):
        if (
            method == 5
            and state("cursor") == 0
            or method == 7
            and not state("editor_step")
            and state("cursor") < 4
        ):
            button("b")
        count = {0: 3, 1: 7, 2: 6, 3: 32, 4: 6, 5: 1, 6: 4, 7: 4, 8: 1}[method]
        focus(count + 1)
        button("a")
        assert state("phase") == 3

    def walk_to(npc, point=None):
        target = content["npcs"][npc]
        start = (state("area"), state("player_x"), state("player_y"))
        queue = deque([(start, [])])
        seen = {start}
        exits = {
            (e["area"], e["x"], e["y"]): (e["to_area"], e["to_x"], e["to_y"])
            for e in content["exits"]
        }
        result = None
        while queue:
            (area, x, y), path = queue.popleft()
            if (point is not None and (area, x, y) == point) or (
                point is None
                and (
                    area == target["area"]
                    and abs(x - target["x"]) <= 2
                    and abs(y - target["y"]) <= 3
                )
            ):
                result = path
                break
            for key, dx, dy in (
                ("left", -1, 0),
                ("right", 1, 0),
                ("up", 0, -1),
                ("down", 0, 1),
            ):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < 20 and 0 <= ny < 14):
                    continue
                if content["areas"][area]["map"][ny][nx] in "#~G":
                    continue
                if any(
                    n["area"] == area
                    and n["x"] <= nx < n["x"] + 2
                    and n["y"] <= ny < n["y"] + 4
                    for n in content["npcs"]
                ):
                    continue
                companion = content["npcs"][0]
                if (
                    area == companion["area"]
                    and companion["x"] + 3 <= nx < companion["x"] + 5
                    and companion["y"] <= ny < companion["y"] + 4
                ):
                    continue
                new = exits.get((area, nx, ny), (area, nx, ny))
                if new not in seen:
                    seen.add(new)
                    queue.append((new, path + [key]))
        assert result is not None, ("NPC unreachable", npc)
        for key in result:
            button(key)
        if point is not None:
            assert (
                state("area"),
                state("player_x"),
                state("player_y"),
            ) == point
            return
        button("a")
        assert state("npc_id") == npc and state("phase") == 6
        finish_opening()

    p = PyBoy(
        str(build / "playground.gbc"), window="null", sound_emulated=False
    )
    try:
        p.set_emulation_speed(0)
        p.tick(180)
        assert state("phase") == 0 and state("ui_id") == 1
        assert symbols["_host_mailbox"] == 0xC800
        assert symbols["s__DATA"] + symbols["l__DATA"] < 0xC800
        capture("world")
        companion = content["npcs"][0]
        walk_to(0, (companion["area"], companion["x"] + 3, companion["y"] + 4))
        before = (state("player_x"), state("player_y"))
        button("up")
        assert (state("player_x"), state("player_y")) == before
        capture("companion-collision")
        walk_to(0)
        # Regression: unmatched completion must not advance an empty ROM string
        # pointer and append adjacent ROM bytes to literal player text.
        for literal in ("z", "vorpax"):
            clear_draft()
            focus(0)
            for char in literal:
                focus(ord(char) - ord("a"))
                button("a")
            before = text()
            focus(30)
            button("a")
            assert text() == before == literal
            assert all(32 <= ord(char) <= 126 for char in text())
            capture(f"unmatched-completion-{literal}")
        clear_draft()
        focus(31)
        button("a")
        button("a")
        focus(1)
        button("a")
        focus(2)
        button("a")
        focus(30)
        button("a")
        assert text() == "12"
        capture("literal-number-completion")
        focus(31)
        button("a")
        button("a")  # Restore lowercase page for later checks.
        clear_draft()
        focus(7)
        button("a")
        focus(30)
        button("a")
        assert text() == "help"
        # Genuine local entry mechanisms, preserving each resulting unsent draft across switches.
        for method in range(8):
            clear_draft()
            mode(method)
            if method == 0:
                button("a")
                button("a")
                button("a")
            elif method == 2:
                button("a")
                assert text() == ""
                focus(8)
                button("a")  # Spell an actual initial before expansion.
                initials = "".join(
                    word[0].lower()
                    for word in content["npcs"][0]["replies"][0][
                        "utterance"
                    ].split()
                )
                type_literal(initials)
                button("b")
                focus(0)
                button("a")
                assert text() == content["npcs"][0]["replies"][0]["utterance"]
            elif method in (1, 3):
                button("a")
            elif method == 4:
                button("a")
                button("a")
            elif method == 5:
                button("up")
                button("a")
            elif method == 6:
                button("a")
                button("a")
                button("a")
            else:
                button("up")
                button("a")
                button("a")
            assert state("draft_length") > 0, method
            capture(f"editor-{method}")
            before = state("committed_count")
            preview(method)
            capture(f"preview-{method}")
            assert state("committed_count") == before
            button("b")
            assert state("phase") == 2
        clear_draft()
        mode(8)
        assert not state("host_available")
        capture("paired-unavailable")
        focus(3)
        button("a")  # Manual spelling remains available without a host.
        button("a")
        assert state("draft_length") == 1
        # Real external text transfer is a WRAM host operation; no game state is injected.
        button("b")
        p.memory[0xC800 + 16] = 1
        p.tick(2)
        focus(0)
        button("a")
        assert state("phase") == 4 and p.memory[0xC800 + 6] == 3
        before_cancel = text()
        button("b")
        assert (
            state("phase") == 2
            and text() == before_cancel
            and p.memory[0xC800 + 5] == 5
        )
        focus(0)
        button("a")
        for heartbeat in range(2, 31):
            p.memory[0xC800 + 16] = heartbeat
            p.tick(120)
        assert state("phase") == 4
        p.memory[0xC800 + 16] = 31
        p.tick(150)
        assert state("phase") == 2 and text() == before_cancel
        p.memory[0xC800 + 16] = 32
        p.tick(2)
        focus(0)
        button("a")
        message = b"I will not trade two crystals."
        for i, value in enumerate(message):
            p.memory[0xC800 + 128 + i] = value
        p.memory[0xC800 + 13] = len(message)
        p.memory[0xC800 + 15] = 3
        p.memory[0xC800 + 5] = 3
        p.tick(20)
        assert state("phase") == 3 and text() == message.decode()
        capture("paired-exact-preview")
        button("b")
        # Explicit authored protocol fixture: stale transfer cannot replace the draft.
        p.memory[0xC800 + 16] = 2
        p.tick(2)
        focus(0)
        button("a")
        assert state("phase") == 4
        before = text()
        rejected = state("rejected_responses")
        p.memory[0xC800 + 7] = (p.memory[0xC800 + 7] + 1) % 256
        p.memory[0xC800 + 5] = 3
        p.tick(20)
        assert state("phase") == 2 and text() == before
        assert state("rejected_responses") == rejected + 1
        # Compose timeout preserves literal text and never enters semantic confirmation.
        p.memory[0xC800 + 16] = 3
        p.tick(2)
        focus(5)
        button("a")
        assert state("phase") == 4 and p.memory[0xC800 + 6] == 2
        for heartbeat in range(4, 21):
            p.memory[0xC800 + 16] = heartbeat
            p.tick(120)
        assert state("phase") == 4
        p.memory[0xC800 + 16] = 21
        p.tick(120)
        assert state("phase") == 2 and text() == before
        # Classification has its own finite frame budget and falls back authored.
        p.memory[0xC800 + 16] = 22
        p.tick(2)
        preview(8)
        button("a")
        assert state("phase") == 4 and p.memory[0xC800 + 6] == 1
        for heartbeat in range(23, 30):
            p.memory[0xC800 + 16] = heartbeat
            p.tick(120)
        assert state("phase") == 4
        p.memory[0xC800 + 16] = 30
        p.tick(120)
        assert state("phase") == 5 and state("source") == 0
        button("b")
        clear_draft()
        mode(3)
        focus(0)
        for _ in range(99):
            button("a")
        assert state("draft_length") == 96 and text() == "a" * 96
        focus(32)
        button("a")
        assert state("draft_length") == 95
        capture("bounded-delete")
        button("b")
        assert state("phase") == 0
        # Wait for heartbeat expiry before testing standalone semantic and quest handling.
        p.tick(250)
        path = [
            (0, "epilogue", False),
            (0, "earth_plan", True),
            (1, "buy_one", True),
            (1, "buy_one", False),
            (2, "correct_name", True),
            (2, "safe_route", True),
            (3, "rescue_scout", True),
            (4, "get_permit", True),
            (0, "epilogue", True),
        ]
        for npc, label, success in path:
            walk_to(npc)
            if npc == 1:
                clear_draft()
                mode(1)
                focus(2)
                button("a")
                focus(3)
                button("a")
                focus(6)
                button("a")
                assert text() == "one two crystal"
                capture("quartermaster-contextual-keywords")
            clear_draft()
            choice = next(
                i
                for i, r in enumerate(content["npcs"][npc]["replies"])
                if r["label"] == label
            )
            message = content["npcs"][npc]["replies"][choice]["utterance"]
            type_literal(message)
            saved_source = state("draft_source")
            preview(3)
            flags, bag = state("quest_flags"), state("inventory")
            button("a")
            assert (
                state("phase") == 5
                and state("quest_flags") == flags
                and state("inventory") == bag
            )
            if state("outcome_id") != choice:
                button("down")
                button("a")
                for _ in range(choice):
                    button("down")
                button("a")
            button("a")
            assert state("phase") == 6
            if success:
                assert text() == ""
            else:
                assert (
                    state("quest_flags") == flags and state("inventory") == bag
                )
                assert (
                    text() == message and state("draft_source") == saved_source
                )
            capture(label if success else f"rejected-{label}")
            button("b")
        assert state("quest_flags") & 128
        assert state("inventory") == 12
        capture("complete-world")
    finally:
        p.stop(save=False)
    report = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "rom_sha256": provenance["rom_sha256"],
        "hardware_verified": False,
        "button_events": events,
        "captures": captures,
        "protocol_fixture": "Explicit authored mailbox responses test transport and stale rejection; no model inference or model accuracy is claimed.",
        "checks": [
            "eight distinct local entry methods",
            "no automatic Send",
            "draft preserved across UI changes",
            "mailbox WRAM separation",
            "paired unavailable manual fallback",
            "real host mailbox transfer exact preview",
            "stale host response rejection",
            "compose timeout preserves draft",
            "operation-specific classification/compose/external frame budgets",
            "B immediately cancels a host wait and preserves draft",
            "96 character limit and visible deletion",
            "unmatched completion preserves unknown names and numbers",
            "matched completion appends only the bounded suffix",
            "NPC contextual keyword chips preserve exact quantities",
            "empty shorthand cannot select a canned phrase",
            "typed full initials expand to an authored exact utterance",
            "guard rejection preserves message and source",
            "Rockitten companion footprint blocks player movement",
            "full story uses literal grid typing and actual walking",
            "connected world traversal",
            "five NPC guarded quest path",
            "inventory spending",
            "epilogue flag",
        ],
    }
    (build / "playground-verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print("Playground verified through actual PyBoy buttons.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    verify(parser.parse_args().build)
