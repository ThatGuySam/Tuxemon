"""Real model + ROM verification through buttons; no game-state writes."""

import argparse
import ast
import hashlib
import json
import re
import secrets
import sys
import threading
import time
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--build", type=Path, default=ROOT / "build/chromatic/playground"
)
parser.add_argument("--output-dir", type=Path)
args = parser.parse_args()
OUT = args.output_dir or args.build / "live-evidence"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
from pyboy import PyBoy

from chromatic_demo import playground_bridge as bridge
from chromatic_demo.npc_picker import GLiClassPicker

ROM_BUILD = args.build.resolve(strict=True)
CONTENT = json.loads(
    (ROOT / "chromatic_demo/worlds/last_ascent.json").read_text()
)
MODEL = ROOT / "venv/chromatic-picker-model"
PICKER = GLiClassPicker.from_local_model(MODEL)


def run_case(kind):
    content = CONTENT
    build = OUT
    symbols = {}
    for line in (ROM_BUILD / "playground.noi").read_text().splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "DEF":
            symbols[words[1]] = int(words[2], 16)
    broker = bridge.Broker(
        content,
        None if kind == "authored-fallback" else PICKER,
        provider="ollama" if kind == "compose" else "authored",
        model="gemma4:26b-mlx" if kind == "compose" else None,
    )
    captures, events = [], []
    keyboard_page = 0
    declaration = next(
        line
        for line in (ROM_BUILD / "playground.c").read_text().splitlines()
        if "keyboard_sets[4]" in line
    )
    keyboard_sets = [
        ast.literal_eval(v)
        for v in re.findall(r'"(?:\\.|[^"\\])*"', declaration)
    ]

    def tick(frames):
        for _ in range(frames):
            p.tick()
            controller.tick()
            if state("phase") == 4:
                time.sleep(0.018)

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
        tick(3)
        p.button_release(name)
        tick(20)
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

    server = None
    result = {"case": kind}
    controller = None
    p = PyBoy(
        str(ROM_BUILD / "playground.gbc"), window="null", sound_emulated=False
    )
    try:
        p.set_emulation_speed(0)
        controller = bridge.Controller(p, broker)
        tick(180)
        walk_to(0)
        clear_draft()
        before = {
            n: state(n)
            for n in ("quest_flags", "inventory", "committed_count")
        }
        if kind == "paired":
            mode(8)
            secret = secrets.token_urlsafe(32)
            server = bridge.paired_server(controller, secret)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            message = "I will not trade two crystals."
            request = Request(
                f"http://127.0.0.1:{server.server_port}/v1/input",
                data=json.dumps({"text": message}).encode(),
                headers={"Authorization": "Bearer " + secret},
            )
            with urlopen(request, timeout=5) as response:
                result["http_status"] = response.status
                result["http_response"] = json.loads(response.read())
            assert state("committed_count") == before["committed_count"]
            focus(0)
            button("a")
            for _ in range(1000):
                if state("phase") != 4:
                    break
                tick(1)
            assert state("phase") == 3 and text() == message
            assert state("draft_source") == 3
            result["literal_text"] = message
        elif kind == "compose":
            mode(3)
            type_literal("one crystal")
            focus(36)
            button("a")
            for _ in range(2400):
                if state("phase") != 4:
                    break
                tick(1)
            result["compose_completed"] = state("phase") == 3
            result["resulting_draft"] = text()
            if state("phase") == 3:
                assert state("draft_source") == 2
                assert controller.last_result.source == 2
                assert controller.last_result.model_id == "gemma4:26b-mlx"
            else:
                assert state("phase") == 2 and text() == "one crystal"
                result["failure"] = (
                    "provider unavailable or rejected; literal draft preserved"
                )
        else:
            mode(3)
            message = content["npcs"][0]["replies"][0]["utterance"]
            type_literal(message)
            preview(3)
            button("a")
            for _ in range(1000):
                if state("phase") != 4:
                    break
                tick(1)
            assert state("phase") == 5
            assert state("source") == (0 if kind == "authored-fallback" else 1)
            result["meaning_index"] = state("outcome_id")
            result["literal_text"] = message
            if kind == "classifier":
                assert controller.last_result.scores
                assert controller.last_result.model_id
                assert controller.last_result.model_revision
            else:
                assert controller.last_result.error
        assert {n: state(n) for n in ("quest_flags", "inventory")} == {
            n: before[n] for n in ("quest_flags", "inventory")
        }
        expected_commits = before["committed_count"] + (
            0 if kind in ("paired", "compose") else 1
        )
        assert state("committed_count") == expected_commits
        result["no_quest_or_inventory_effects_before_meaning_confirmation"] = (
            True
        )
        result["committed_count"] = state("committed_count")
        tick(
            30
        )  # The ROM text renderer spans frames; capture after its full redraw.
        capture(kind)
        result["captures"] = captures
        result["button_events"] = events
        if controller.last_result is not None:
            result["broker_result"] = asdict(controller.last_result)
        return result
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if controller is not None:
            controller.close()
        p.stop(save=False)


if __name__ == "__main__":
    report = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "rom_sha256": hashlib.sha256(
            (ROM_BUILD / "playground.gbc").read_bytes()
        ).hexdigest(),
        "hardware_verified": False,
        "game_state_injected": False,
        "cases": [],
    }
    for case in ("classifier", "paired", "compose", "authored-fallback"):
        report["cases"].append(run_case(case))
        (OUT / "real-model-rom-e2e.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(case + ": verified", flush=True)
