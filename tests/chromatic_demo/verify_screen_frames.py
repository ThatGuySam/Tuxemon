"""Trace each LCD frame across shared renderer screens and shorter draft edits."""

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import secrets
import sys
import threading
import time
from collections import deque
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from pyboy import PyBoy

if not __debug__:
    raise RuntimeError(
        "Screen verification requires enabled Python assertions; omit -O"
    )


def verify(
    build: Path,
    output_dir: Path | None = None,
    smoke: bool = False,
    bridge_path: Path | None = None,
) -> None:
    symbols = {}
    for line in (build / "playground.noi").read_text().splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "DEF":
            symbols[words[1]] = int(words[2], 16)
    directory = output_dir or build / "screen-verification"
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "coverage.json").exists():
        raise ValueError("Use a fresh isolated evidence directory")
    traces = []
    coverage_phases = set()
    coverage_methods = set()
    coverage_areas = set()
    coverage_paths = set()
    total_frames = 0
    controller = None
    controller_enabled = False
    server = None
    server_thread = None
    fixture_broker = None
    bridge_dependency = None
    status = "running"
    failure = None
    content = json.loads((build / "playground-provenance.json").read_text())[
        "content"
    ]
    compiled_source = (build / "playground.c").read_text()
    phase_match = re.search(r"enum\s*\{([^}]+)\}\s*;", compiled_source)
    if not phase_match:
        raise ValueError("Compiled source lacks a supported phase enum")
    phase_names = [
        name.strip()
        for name in phase_match.group(1).split(",")
        if name.strip()
    ]
    if not all(re.fullmatch(r"[A-Z][A-Z0-9_]*", name) for name in phase_names):
        raise ValueError(
            "Explicit phase enum assignments are unsupported; update the driver"
        )
    phase_ids = {name: index for index, name in enumerate(phase_names)}
    mode_match = re.search(
        r"modes\[(\d+)\]\s*=\s*\{([^}]+)\}", compiled_source
    )
    if not mode_match:
        raise ValueError(
            "Compiled source lacks a supported literal method table"
        )
    method_count = int(mode_match.group(1))
    method_names = [
        ast.literal_eval(value)
        for value in re.findall(r'"(?:\\.|[^"\\])*"', mode_match.group(2))
    ]
    if len(method_names) != method_count:
        raise ValueError(
            "Method table count does not match its declared labels"
        )
    area_count = len(content["areas"])
    digest = hashlib.sha256(
        (build / "playground.gbc").read_bytes()
    ).hexdigest()
    if (
        digest
        != json.loads((build / "playground-provenance.json").read_text())[
            "rom_sha256"
        ]
    ):
        raise ValueError("ROM hash disagrees with exact bundle provenance")
    p = PyBoy(
        str(build / "playground.gbc"), window="null", sound_emulated=False
    )
    boot_ready = False
    frame_log = None
    action_log = None
    try:
        p.set_emulation_speed(0)
        p.tick(180)
        frame_log = (directory / "frames.jsonl").open("w")
        action_log = (directory / "actions.jsonl").open("w")
        boot_ready = True
    finally:
        if not boot_ready:
            if frame_log:
                frame_log.close()
            if action_log:
                action_log.close()
            p.stop(save=False)

    def state(name):
        return p.memory[symbols["_" + name]]

    def header():
        return np.asarray(p.screen.image)[:16, :, :3].tobytes()

    def snapshot():
        names = (
            "phase",
            "ui_id",
            "area",
            "player_x",
            "player_y",
            "npc_id",
            "cursor",
            "draft_length",
            "quest_flags",
            "inventory",
            "committed_count",
            "source",
            "editor_step",
            "editor_group",
            "spelling",
            "draft_revision",
        )
        result = {name: state(name) for name in names}
        result["draft"] = bytes(
            p.memory[symbols["_draft"] + i]
            for i in range(state("draft_length"))
        ).decode("ascii")
        return result

    def image(name):
        path = directory / name
        p.screen.image.save(path)
        return path.name

    def tick(
        action_id,
        frame,
        stable_pixels=None,
        stable_phase=None,
        label_pixels=None,
        label_mask=None,
        label_state=None,
    ):
        nonlocal total_frames
        p.tick(1)
        if controller_enabled:
            controller.tick()
            time.sleep(0)
        total_frames += 1
        array = np.asarray(p.screen.image)
        dark = int(np.any(array[:, :, :3] < 100, axis=2).sum())
        record = {
            "frame": total_frames,
            "action_id": action_id,
            "action_frame": frame,
            "dark_pixels": dark,
            "lcdc": p.memory[0xFF40],
            "phase": state("phase"),
            "method": state("ui_id"),
            "area": state("area"),
            "header_pixels_sha256": hashlib.sha256(header()).hexdigest(),
        }
        frame_log.write(json.dumps(record) + "\n")
        coverage_phases.add(state("phase"))
        if state("phase") == 0:
            coverage_areas.add(state("area"))
        if state("phase") == 2:
            coverage_methods.add(state("ui_id"))
        reason = None
        if dark == 0:
            reason = "all-white frame"
        elif not p.memory[0xFF40] & 0x80:
            reason = "LCD was disabled"
        elif (
            stable_pixels is not None
            and (stable_phase is None or state("phase") == stable_phase)
            and header() != stable_pixels
        ):
            reason = "stable header was erased or changed in actual LCD pixels"
        elif label_pixels is not None:
            current = snapshot()
            same = all(
                current[name] == label_state[name]
                for name in (
                    "phase",
                    "ui_id",
                    "editor_step",
                    "editor_group",
                    "spelling",
                    "draft_revision",
                )
            )
            if current["phase"] == 1:
                same = same and max(
                    0, min(5, label_state["cursor"] - 6)
                ) == max(0, min(5, current["cursor"] - 6))
            if same and not np.array_equal(
                array[label_mask], label_pixels[label_mask]
            ):
                reason = "unchanged body labels were erased or changed in actual LCD pixels"
        if reason:
            record["reason"] = reason
            record["screenshot"] = image(
                f"failure-{action_id:05}-{frame:04}.png"
            )
            (directory / "failure.json").write_text(
                json.dumps(record, indent=2) + "\n"
            )
            raise AssertionError(reason)
        return record

    def event(key, name=None, stable_header=False):
        old_header = header()
        frames = []
        action_id = len(traces) + 1
        name = name or f"button-{key}"
        action = {
            "id": action_id,
            "name": name,
            "key": key,
            "before": snapshot(),
            "before_png": image(f"{action_id:05}-{name}-before.png"),
            "stable_header_pixels": stable_header,
        }
        label_pixels = None
        label_mask = None
        if (
            key in ("up", "down", "left", "right")
            and state("phase") != 0
            and not (state("phase") == 2 and state("ui_id") == 5)
        ):
            label_pixels = np.asarray(p.screen.image).copy()
            label_mask = np.ones(label_pixels.shape[:2], dtype=bool)
            label_mask[:16] = False
            label_mask[:, 0:8] = False
            label_mask[112:136, 80:88] = False
            if state("phase") == 2 and (
                state("ui_id") == 3 or state("spelling")
            ):
                for column in range(0, 160, 16):
                    label_mask[56:80, column : column + 8] = False
        traces.append(action)
        p.button_press(key)
        try:
            for frame in range(1, 21):
                frames.append(
                    tick(
                        action_id,
                        frame,
                        old_header if stable_header else None,
                        label_pixels=label_pixels,
                        label_mask=label_mask,
                        label_state=action["before"],
                    )
                )
                if frame == 2:
                    p.button_release(key)
        finally:
            p.button_release(key)
            action["after"] = snapshot()
            action["after_png"] = image(f"{action_id:05}-{name}-after.png")
            action["frames"] = len(frames)
            action_log.write(json.dumps(action) + "\n")
        assert bool(p.memory[0xFF40] & 2) == (state("phase") == 0)

    def idle(frames, name):
        action_id = len(traces) + 1
        stable = header()
        phase = state("phase")
        action = {
            "id": action_id,
            "name": name,
            "key": None,
            "before": snapshot(),
            "before_png": image(f"{action_id:05}-{name}-before.png"),
            "frames": 0,
        }
        traces.append(action)
        try:
            for frame in range(1, frames + 1):
                tick(action_id, frame, stable, phase)
                action["frames"] += 1
        finally:
            action["after"] = snapshot()
            action["after_png"] = image(f"{action_id:05}-{name}-after.png")
            action_log.write(json.dumps(action) + "\n")

    def mark(path):
        coverage_paths.add(path)

    def focus(index):
        if state("phase") == 2 and (state("ui_id") == 3 or state("spelling")):
            queue = deque([(state("cursor"), [])])
            seen = set()
            while queue:
                cursor, path = queue.popleft()
                if cursor == index:
                    for direction in path:
                        event(direction, stable_header=True)
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
                    queue.append((destination, path + [direction]))
        for _ in range(50):
            if state("cursor") == index:
                return
            event("right", stable_header=True)
        raise AssertionError("Unreachable editor focus")

    def mode(method):
        event("start", f"editor-{method}-pause")
        rank = [1, 0, 2, 3, 4, 5, 6, 7, 8].index(method)
        while state("cursor") != rank:
            event("down", stable_header=True)
        event("a", f"editor-{method}-switch")
        assert state("phase") == 2 and state("ui_id") == method

    def clear():
        mode(3)
        focus(32)
        while state("draft_length"):
            event("a", stable_header=True)

    def text():
        return snapshot()["draft"]

    def walk_to(npc):
        target = content["npcs"][npc]
        start = (state("area"), state("player_x"), state("player_y"))
        queue = deque([(start, [])])
        seen = {start}
        exits = {
            (item["area"], item["x"], item["y"]): (
                item["to_area"],
                item["to_x"],
                item["to_y"],
            )
            for item in content["exits"]
        }
        while queue:
            position, path = queue.popleft()
            area, x, y = position
            if (
                area == target["area"]
                and abs(x - target["x"]) <= 2
                and abs(y - target["y"]) <= 3
            ):
                for direction in path:
                    event(direction, "walk-" + direction)
                return
            for direction, dx, dy in (
                ("left", -1, 0),
                ("right", 1, 0),
                ("up", 0, -1),
                ("down", 0, 1),
            ):
                nx, ny = x + dx, y + dy
                if (
                    not (0 <= nx < 20 and 0 <= ny < 14)
                    or content["areas"][area]["map"][ny][nx] in "#~G"
                ):
                    continue
                if any(
                    item["area"] == area
                    and item["x"] <= nx < item["x"] + 2
                    and item["y"] <= ny < item["y"] + 4
                    for item in content["npcs"]
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
                    queue.append((new, path + [direction]))
        raise AssertionError("NPC area unreachable through real movement")

    required_paths = {
        "menu.cursor",
        "menu.scroll",
        "menu.wrap",
        "reply.opening",
        "reply.paginate",
        "reply.done",
        "reply.back",
        "draft.shorter_delete",
        "draft.limit96",
        "font.ascii95",
        "preview.send",
        "preview.edit",
        "preview.cancel",
        "meaning.pick",
        "meaning.confirm",
        "meaning.edit",
        "meaning.cancel",
        "world.areas",
        "journal",
        "reset",
        "paired.unavailable",
        "paired.manual",
        "paired.http",
        "wait.external",
        "wait.cancel",
        "wait.external.timeout",
        "wait.compose",
        "wait.classify",
    }
    required_paths.update(f"editor.{method}" for method in range(method_count))
    required_paths.update(
        f"wait.{operation}.{outcome}"
        for operation in ("compose", "classify")
        for outcome in ("response", "error", "timeout")
    )

    required_paths.update(f"npc.{npc}" for npc in range(len(content["npcs"])))

    class SmokeComplete(Exception):
        pass

    try:
        if smoke:
            event("start", "smoke-open-menu")
            assert state("phase") == 1
            event("down", "smoke-menu-down", True)
            mark("menu.cursor")
            raise SmokeComplete
        event("start", "world-to-menu")
        event("down", "menu-cursor", True)
        mark("menu.cursor")
        for _ in range(6):
            event("down", stable_header=True)
        event("down", "menu-scroll", True)
        mark("menu.scroll")
        while state("cursor") != 11:
            event("down", stable_header=True)
        event("down", "menu-wrap", True)
        assert state("cursor") == 0
        mark("menu.wrap")
        event("b", "menu-to-world")
        event("up", "approach-npc")
        event("a", "world-to-reply")
        while state("phase") == 6:
            event("a", "reply-page")
        mark("reply.opening")
        assert state("phase") == 2
        for method in range(8):
            clear()
            mode(method)
            if method == 0:
                event("down", "intent-cursor", True)
                event("a", "intent-topic", True)
                event("a", "intent-stance", True)
                event("a", "intent-draft", True)
            elif method == 1:
                event("down", "keyword-cursor", True)
                event("a", "keyword-draft", True)
            elif method == 2:
                focus(8)
                event("a", "shorthand-spell")
                focus(15)
                event("a", "shorthand-initial", True)
                event("b", "shorthand-expansions")
                focus(0)
                event("a", "shorthand-draft", True)
            elif method == 3:
                event("right", "grid-cursor", True)
                event("a", "grid-draft", True)
            elif method == 4:
                event("a", "group-open", True)
                event("right", "group-letter-cursor", True)
                event("a", "group-letter", True)
            elif method == 5:
                event("up", "gesture-stroke", True)
                event("a", "gesture-letter", True)
            elif method == 6:
                event("a", "dasher-zoom-1", True)
                event("a", "dasher-zoom-2", True)
                event("a", "dasher-letter", True)
            else:
                event("up", "radial-petal", True)
                event("a", "radial-open", True)
                event("a", "radial-letter", True)
            assert state("draft_length") > 0
            mark(f"editor.{method}")
        clear()
        mode(3)
        focus(0)
        for index in range(16):
            focus(index)
            event("a", stable_header=True)
        assert state("draft_length") == 16
        focus(32)
        for _ in range(14):
            event("a", stable_header=True)
        event("a", "delete-shorter-tail", True)
        assert state("draft_length") == 1
        mark("draft.shorter_delete")
        blank = p.memory[0x9800 + 3 * 32]
        assert all(
            p.memory[0x9800 + 2 * 32 + x] == blank for x in range(2, 20)
        )
        assert all(
            p.memory[0x9800 + y * 32 + x] == blank
            for y in (3, 4)
            for x in range(20)
        )
        # Verify every printable ASCII glyph against the encoding learned via
        # public GBDK font calls, using actual grid navigation and character entry.
        declaration = next(
            line
            for line in (build / "playground.c").read_text().splitlines()
            if "keyboard_sets[4]" in line
        )
        keyboard_sets = [
            ast.literal_eval(value)
            for value in re.findall(r'"(?:\\.|[^"\\])*"', declaration)
        ]
        keyboard_page = 0

        def glyph_button(key):
            event(key, "ascii-button-" + key, True)

        def glyph_focus(index):
            focus(index)

        for code in range(32, 127):
            glyph_focus(32)
            glyph_button("a")
            page, index = next(
                (page, chars.index(chr(code)))
                for page, chars in enumerate(keyboard_sets)
                if chr(code) in chars
            )
            while keyboard_page != page:
                glyph_focus(31)
                glyph_button("a")
                keyboard_page = (keyboard_page + 1) % 4
            glyph_focus(index)
            glyph_button("a")
            assert (
                state("draft_length") == 1
                and p.memory[symbols["_draft"]] == code
            )
            assert (
                p.memory[0x9800 + 2 * 32 + 1]
                == p.memory[symbols["_font_tiles"] + code - 32]
            ), code
        mark("font.ascii95")
        focus(33)
        event("a", "editor-to-preview")
        event("down", "preview-cursor", True)
        event("up", stable_header=True)
        event("a", "preview-to-meaning")
        assert state("phase") == 5
        event("down", "meaning-cursor", True)
        event("a", "meaning-list", True)
        event("a", "meaning-confirm", True)
        event("a", "meaning-to-reply")
        event("b", "reply-to-world")
        event("right", "world-move", True)
        mark("preview.send")
        mark("meaning.pick")
        mark("meaning.confirm")
        mark("reply.back")
        for npc in (1, 2, 3, 4, 0):
            walk_to(npc)
            event("a", f"npc-{npc}-opening")
            assert state("npc_id") == npc and state("phase") == 6
            while state("phase") == 6:
                event("a", f"npc-{npc}-opening-next")
            assert state("phase") == 2
            event("down", f"npc-{npc}-editor-cursor", True)
            mark(f"npc.{npc}")
            event("b", f"npc-{npc}-editor-back")
        assert coverage_areas == set(range(area_count))
        mark("world.areas")
        event("start", "open-journal-menu")
        while state("cursor") != 9:
            event("down", stable_header=True)
        event("a", "journal")
        assert state("phase") == 7
        mark("journal")
        event("a", "journal-back")
        while state("cursor") != 10:
            event("down", stable_header=True)
        event("a", "reset-world")
        assert (
            state("phase") == 0
            and state("quest_flags") == 0
            and state("inventory") == 3
        )
        mark("reset")
        walk_to(0)
        event("a", "open-editor")
        while state("phase") == 6:
            event("a", "opening-next")
        clear()
        mode(3)
        while keyboard_page != 0:
            focus(31)
            event("a", stable_header=True)
            keyboard_page = (keyboard_page + 1) % 4
        focus(0)
        for _ in range(97):
            event("a", "draft-limit", True)
        assert state("draft_length") == 96
        mark("draft.limit96")
        clear()
        focus(0)
        event("a", "literal-draft", True)
        focus(33)
        event("a", "preview-edit")
        event("b", "preview-back")
        assert state("phase") == 2
        mark("preview.edit")
        focus(33)
        event("a", "preview-cancel")
        event("down", stable_header=True)
        event("down", stable_header=True)
        event("a", "preview-cancel-world")
        assert state("phase") == 0
        mark("preview.cancel")
        event("a", "reopen-editor")
        while state("phase") == 6:
            event("a", "opening-next")
        clear()
        focus(0)
        event("a", stable_header=True)
        mode(8)
        assert state("host_available") == 0
        mark("paired.unavailable")
        focus(3)
        event("a", "paired-manual-spell")
        focus(1)
        event("a", "paired-manual-input", True)
        assert state("draft_length") > 0
        mark("paired.manual")
        event("b", "paired-manual-back")
        path = (
            bridge_path
            or Path(__file__).resolve().parents[2]
            / "chromatic_demo/playground_bridge.py"
        )
        bridge_dependency = {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        spec = importlib.util.spec_from_file_location(
            "owned_verification_bridge", path
        )
        bridge = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = bridge
        spec.loader.exec_module(bridge)

        class BoundaryBroker:
            """Labeled delay/error fixtures wrap the actual authored Broker."""

            def __init__(self):
                self.real = bridge.Broker(content)
                self.gate = threading.Event()
                self.gate.set()
                self.error = False

            def run(self, turn):
                gate, error = self.gate, self.error
                gate.wait()
                if error:
                    raise ValueError(
                        "Explicit verification-boundary error fixture"
                    )
                return self.real.run(turn)

            def configure(self, error=False):
                self.error = error
                self.gate = threading.Event()

        fixture_broker = BoundaryBroker()
        controller = bridge.Controller(p, fixture_broker)
        controller_enabled = True
        secret = secrets.token_urlsafe(24)
        server = bridge.paired_server(controller, secret)
        server_thread = threading.Thread(
            target=server.serve_forever, daemon=True
        )
        server_thread.start()
        idle(3, "host-handshake")
        focus(0)
        event("a", "paired-receive-wait")
        assert state("phase") == 4
        mark("wait.external")
        authored = "I want a cautious plan."
        request = Request(
            f"http://127.0.0.1:{server.server_port}/v1/input",
            data=json.dumps({"text": authored}).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + secret,
            },
        )
        with urlopen(request, timeout=5) as response:
            receipt = json.loads(response.read())
            assert response.status == 202 and receipt["committed"] is False
        (directory / "paired-http.json").write_text(
            json.dumps(
                {
                    "transport": "owned ephemeral loopback HTTP",
                    "method": "POST",
                    "path": "/v1/input",
                    "auth": "ephemeral verification secret omitted",
                    "request_text": authored,
                    "response_status": 202,
                    "response_body": receipt,
                    "provenance": "Authored verification input, not model-generated output",
                },
                indent=2,
            )
            + "\n"
        )
        idle(20, "paired-http-delivery")
        assert state("phase") == 3 and text() == authored
        mark("paired.http")
        event("b", "paired-edit-back")
        focus(0)
        event("a", "paired-cancel-wait")
        assert state("phase") == 4
        preserved = text()
        event("b", "paired-cancel")
        assert state("phase") == 2 and text() == preserved
        mark("wait.cancel")
        focus(0)
        event("a", "paired-timeout-wait")
        idle(3620, "paired-timeout")
        assert state("phase") == 2 and text() == preserved
        mark("wait.external.timeout")
        for operation, limit in (("compose", 2100), ("classify", 900)):
            for outcome in ("response", "error", "timeout"):
                fixture_broker.configure(error=outcome == "error")
                if operation == "compose":
                    focus(5)
                    event("a", f"{operation}-{outcome}-wait")
                else:
                    focus(2)
                    event("a", "classifier-preview")
                    event("a", f"{operation}-{outcome}-wait")
                assert state("phase") == 4
                mark("wait." + operation)
                saved = text()
                if outcome == "timeout":
                    idle(limit + 20, f"{operation}-timeout")
                else:
                    fixture_broker.gate.set()
                    idle(30, f"{operation}-{outcome}")
                expected = (
                    2
                    if operation == "compose" and outcome != "response"
                    else 3
                    if operation == "compose"
                    else 5
                )
                assert state("phase") == expected and text() == saved, (
                    operation,
                    outcome,
                    snapshot(),
                )
                mark(f"wait.{operation}.{outcome}")
                fixture_broker.gate.set()
                idle(20, "drain-stale-worker")
                if state("phase") == 3:
                    event("b", "host-preview-back")
                elif state("phase") == 5:
                    if outcome == "response":
                        event("down", stable_header=True)
                        event("down", stable_header=True)
                        event("a", "meaning-edit")
                        assert state("phase") == 2
                        mark("meaning.edit")
                    else:
                        event("b", "meaning-cancel")
                        assert state("phase") == 2
                        mark("meaning.cancel")
        focus(2)
        event("a", "final-preview")
        event("a", "final-meaning-wait")
        idle(30, "final-meaning")
        assert state("phase") == 5
        event("down", stable_header=True)
        event("a", "choose-authored-meaning")
        event("a", "select-earth-plan")
        event("a", "confirm-earth-plan")
        assert state("phase") == 6
        old_page = state("reply_page")
        event("a", "reply-pagination")
        assert state("phase") == 6 and state("reply_page") > old_page
        mark("reply.paginate")
        while state("phase") == 6:
            event("a", "reply-finish")
        assert state("phase") == 0
        mark("reply.done")
        mark("editor.8")
        missing_paths = required_paths - coverage_paths
        assert (
            coverage_phases == set(phase_ids.values())
            and coverage_methods == set(range(method_count))
            and not missing_paths
        ), (
            "Incomplete enumerated coverage",
            sorted(coverage_phases),
            sorted(coverage_methods),
            sorted(missing_paths),
        )
        status = "passed"
    except SmokeComplete:
        status = "passed"
    except Exception as error:
        status = "failed"
        failure = str(error)
        if not (directory / "failure.json").exists():
            (directory / "failure.json").write_text(
                json.dumps(
                    {
                        "reason": failure,
                        "state": snapshot(),
                        "screenshot": image("failure-final.png"),
                    },
                    indent=2,
                )
                + "\n"
            )
        raise
    finally:
        if fixture_broker:
            fixture_broker.gate.set()
        if server:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)
        if controller:
            controller.close()
        p.stop(save=False)
        frame_log.close()
        action_log.close()
        report = {
            "status": status,
            "failure": failure,
            "rom_sha256": digest,
            "smoke": smoke,
            "bridge_dependency": bridge_dependency,
            "coverage_enforced": not smoke,
            "observed_phases": sorted(coverage_phases),
            "observed_methods": sorted(coverage_methods),
            "observed_areas": sorted(coverage_areas),
            "observed_paths": sorted(coverage_paths),
            "action_count": len(traces),
            "checked_frame_count": total_frames,
            "declared_phase_ids": phase_ids,
            "declared_method_names": method_names,
            "required_phases": list(phase_ids.values())
            if not smoke
            else [phase_ids["WORLD"], phase_ids["MENU"]],
            "required_methods": list(range(method_count)) if not smoke else [],
            "required_areas": list(range(area_count)) if not smoke else [],
            "required_paths": sorted(required_paths)
            if not smoke
            else ["menu.cursor"],
            "missing_paths": sorted(required_paths - coverage_paths)
            if not smoke
            else sorted({"menu.cursor"} - coverage_paths),
            "cleanup": {
                "emulator_stopped_save_false": True,
                "owned_http_server_closed": server is not None,
            },
            "proof_scope": "Concrete enumerated emulator paths, not every possible input history or physical LCD behavior. Boot initialization excluded. No physical device/browser/SDL session used.",
            "host_scope": "Not exercised in menu-only smoke"
            if smoke
            else "Actual owned Controller and real loopback HTTP transfer. Authored Broker responses with explicitly gated delay/error fixtures; no live-model inference or latency claim.",
        }
        (directory / "coverage.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
    print(
        json.dumps(
            {
                "status": status,
                "actions": len(traces),
                "checked_frames": total_frames,
                "coverage": str(directory / "coverage.json"),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--bridge", type=Path)
    args = parser.parse_args()
    verify(args.build, args.output_dir, args.smoke, args.bridge)
