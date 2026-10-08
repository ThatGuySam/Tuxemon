# SPDX-License-Identifier: GPL-3.0-or-later

import errno
import json
import os
import select
import signal
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX PTY required"
)
if sys.platform != "win32":
    import fcntl
    import pty
    import termios

import pyte

ROOT = Path(__file__).resolve().parents[2]
KEYS = {
    "enter": b"\r",
    "down": b"\x1bOB",
    "up": b"\x1bOA",
    "right": b"\x1bOC",
    "left": b"\x1bOD",
    "tab": b"\t",
    "backspace": b"\x7f",
    "escape": b"\x1b",
    "quit": b"\x03",
    "f1": b"\x1bOP",
}


class Screen(pyte.Screen):
    # ncurses uses ECMA-48 SU/SD, which pyte 0.8.2 does not dispatch.
    def scroll_up(self, count=1):
        saved = self.cursor.y
        self.cursor.y = self.margins.bottom if self.margins else self.lines - 1
        for _ in range(count or 1):
            self.index()
        self.cursor.y = saved

    def scroll_down(self, count=1):
        saved = self.cursor.y
        self.cursor.y = self.margins.top if self.margins else 0
        for _ in range(count or 1):
            self.reverse_index()
        self.cursor.y = saved


class Stream(pyte.ByteStream):
    csi = {**pyte.ByteStream.csi, "S": "scroll_up", "T": "scroll_down"}
    events = pyte.ByteStream.events | {"scroll_up", "scroll_down"}


class Terminal:
    def __init__(
        self, name, provider="authored", model=None, env=None, ollama_url=None
    ):
        base = Path(
            os.environ.get(
                "TERMINAL_E2E_EVIDENCE", ROOT / "build/chromatic/terminal-e2e"
            )
        )
        self.directory = base / f"{name}-{uuid.uuid4().hex[:10]}"
        self.directory.mkdir(parents=True)
        self.actions = []
        self.raw = bytearray()
        self.screen = Screen(120, 40)
        self.stream = Stream(self.screen)
        self.master, slave = pty.openpty()
        fcntl.ioctl(
            slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0)
        )
        command = [
            sys.executable,
            "-m",
            "chromatic_demo.terminal",
            "--provider",
            provider,
        ]
        if ollama_url:
            command += ["--ollama-url", ollama_url]
        if model:
            command += ["--model", model]
        environment = {
            **os.environ,
            "TERM": "xterm-256color",
            "PYTHONUNBUFFERED": "1",
            "PYTHONOPTIMIZE": "",
            **(env or {}),
        }

        def own_terminal():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

        self.process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=environment,
            preexec_fn=own_terminal,
        )
        os.close(slave)
        self.actions.append(
            {
                "command": command,
                "cwd": str(ROOT),
                "pid": self.process.pid,
                "provider": provider,
            }
        )

    @property
    def text(self):
        return "\n".join(line.rstrip() for line in self.screen.display)

    def pump(self, duration=0.08):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            ready, _, _ = select.select(
                [self.master], [], [], max(0, deadline - time.monotonic())
            )
            if not ready:
                break
            try:
                chunk = os.read(self.master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            self.raw.extend(chunk)
            self.stream.feed(chunk)

    def record(self, action):
        self.actions.append({"action": action, "screen": self.text})
        (self.directory / "actions.json").write_text(
            json.dumps(self.actions, indent=2)
        )
        (self.directory / "terminal.raw").write_bytes(self.raw)
        (self.directory / "screen.txt").write_text(self.text)

    def press(self, key, count=1):
        os.write(self.master, KEYS.get(key, key.encode("ascii")) * count)
        self.pump()
        self.record(f"press {key!r} x{count}")

    def expect(self, fragment, timeout=3):
        deadline = time.monotonic() + timeout
        while fragment not in self.text and time.monotonic() < deadline:
            self.pump()
        self.record(f"expect {fragment!r}")
        assert fragment in self.text, (
            f"Expected visible {fragment!r}; evidence: {self.directory}\nActual screen:\n{self.text}"
        )

    def choose(self, label, activation=None):
        for _ in range(80):
            if f"> {label}\n" in self.text + "\n":
                self.press(activation or getattr(self, "activation", "enter"))
                return
            self.press("down" if "| npc_reply" in self.text else "right")
        pytest.fail(f"Could not select {label!r}:\n{self.text}")

    def menu(self, label):
        self.press("f1")
        self.expect("| menu")
        self.choose(label)

    def scene(self, name):
        self.menu("Scenarios")
        for _ in range(5):
            if f"> {name}:" in self.text:
                self.press("enter")
                self.expect(f"{name} |")
                return
            self.press("down")
        pytest.fail(f"Scenario missing: {name}")

    def type_text(self, text):
        self.press("tab")
        self.expect("KEYBOARD: letters type")
        self.press(text)
        self.expect(f"|{text}|")

    def journal(self):
        self.menu("Journal")
        self.expect("Items:")

    def close(self):
        try:
            if self.process.poll() is None:
                self.press("quit")
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGTERM)
                    self.process.wait(timeout=3)
            self.pump()
            self.record(f"exit {self.process.returncode}")
        finally:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
            os.close(self.master)


@pytest.fixture
def terminal(request):
    app = Terminal(request.node.name)
    try:
        app.expect("CHROMATIC TEXT LAB")
        yield app
    finally:
        app.close()


def test_return_selects_scenarios_from_start_menu(terminal):
    terminal.press("f1")
    terminal.expect("| menu")
    terminal.press("down")
    terminal.expect("> Scenarios")
    terminal.press("enter")
    terminal.expect("| scenarios")
    terminal.press("enter")
    terminal.expect("Professor | BUTTONS")
    terminal.expect("| editor")


def test_screen_decoder_scroll_region():
    screen = Screen(8, 5)
    stream = Stream(screen)
    stream.feed(b"\x1b[1;1HA\x1b[2;1HB\x1b[3;1HC\x1b[4;1HD\x1b[5;1HE")
    stream.feed(b"\x1b[2;4r\x1b[3;3H\x1b[1S")
    assert [row.strip() for row in screen.display] == ["A", "C", "D", "", "E"]
    assert (screen.cursor.x, screen.cursor.y) == (2, 2)
    stream.feed(b"\x1b[T")
    assert [row.strip() for row in screen.display] == ["A", "", "C", "D", "E"]
    assert (screen.cursor.x, screen.cursor.y) == (2, 2)


@pytest.mark.parametrize(
    "method,keys,expected",
    [
        ("Keyword chips", ["a"], "ask"),
        (
            "Intent composer",
            ["a", "a", "a"],
            "Can we discuss this: Trade for one pack?",
        ),
        (
            "Initials shorthand",
            [],
            "Trade my crystal for exactly one supply pack.",
        ),
        ("Predictive grid", ["a"], "a"),
        ("Grouped alphabet", ["a", "a"], "a"),
        ("Custom EdgeWrite", ["up", "a"], "a"),
        ("Dasher inspired tree", ["right", "a", "a", "a"], "h"),
        ("Radial groups", ["right", "a", "a"], "h"),
        ("Host keyboard", ["a", "sample", "tab"], "sample"),
    ],
)
@pytest.mark.parametrize("activation", ["a", "enter"])
def test_every_method_real_input_and_preview(
    terminal, method, keys, expected, activation
):
    terminal.activation = activation
    terminal.menu("Input methods")
    terminal.choose(method)
    terminal.expect(f"{method} |")
    if method == "Initials shorthand":
        terminal.press("backspace")
        terminal.choose("SPELL")
        terminal.choose("t")
        terminal.press("s")
        terminal.choose("Trade for one pack")
    else:
        for key in keys:
            terminal.press(activation if key == "a" else key)
    terminal.expect(f"|{expected}|")
    terminal.press("backspace")
    terminal.choose("PREVIEW")
    terminal.expect("| preview")
    terminal.expect(f"EXACT TEXT: |{expected}|")
    terminal.press("enter")
    terminal.expect("| meaning")
    terminal.choose("None of these / clarify")
    terminal.expect("| confirm")
    terminal.expect("No quest changes occur until you confirm.")
    terminal.press("enter")
    terminal.expect("Meaning unresolved.")
    terminal.journal()
    terminal.expect("Items: aid_kit, crystal")
    assert "[done]" not in terminal.text


def test_keyboard_limit_toggle_and_back_navigation(terminal):
    terminal.type_text("a" * 96)
    terminal.expect("Draft (96/96)")
    terminal.press("z")
    terminal.expect("Draft (96/96)")
    assert "|" + "a" * 96 + "z|" not in terminal.text
    terminal.press("backspace")
    terminal.expect("Draft (95/96)")
    terminal.press("s")
    terminal.expect("|" + "a" * 95 + "s|")
    terminal.press("tab")
    terminal.expect("Quartermaster | BUTTONS")
    terminal.press("tab")
    terminal.press("enter")
    terminal.expect("| preview")
    terminal.press("escape")
    terminal.expect("| editor")
    terminal.expect("Draft (96/96)")


def conversation(app, text, meaning):
    app.type_text(text)
    app.press("enter")
    app.expect("| preview")
    app.expect(f"EXACT TEXT: |{text}|")
    app.press("enter")
    app.expect("| meaning")
    app.choose(meaning)
    app.expect("| confirm")
    app.expect("No quest changes occur until you confirm.")
    app.press("enter")
    app.expect("| reply")
    app.press("enter")
    app.expect("| editor")
    app.press("tab")


def test_refusal_and_confirmed_trade_item_guard(terminal):
    conversation(terminal, "Do not trade my crystal.", "Decline the trade")
    terminal.journal()
    terminal.expect("Items: aid_kit, crystal")
    terminal.expect("[ ] One supply pack reserved")
    terminal.press("enter")
    terminal.type_text("Exactly one pack, not two.")
    terminal.press("enter")
    terminal.press("enter")
    terminal.choose("Trade for one pack")
    terminal.expect("| confirm")
    terminal.journal()
    terminal.expect("Items: aid_kit, crystal")
    terminal.expect("[ ] One supply pack reserved")
    terminal.press("enter")
    terminal.press("enter")
    terminal.press("enter")
    terminal.choose("Trade for one pack")
    terminal.press("enter")
    terminal.expect("One crystal for one supply pack, agreed.")
    terminal.journal()
    terminal.expect("Items: aid_kit, supply_pack")
    terminal.expect("[done] One supply pack reserved")
    terminal.press("enter")
    terminal.press("tab")
    conversation(terminal, "Trade for another pack.", "Trade for one pack")
    terminal.expect("That choice needs a different quest state.")
    terminal.journal()
    terminal.expect("Items: aid_kit, supply_pack")


def test_complete_quest_through_scenarios(terminal):
    for scene, text, meaning in [
        (
            "Quartermaster",
            "Trade my crystal for one supply pack.",
            "Trade for one pack",
        ),
        ("Tracker Iona", "The name is Lumi, not Luma.", "Correct tag name"),
        ("Tracker Iona", "Mark the dry route.", "Confirm dry trail"),
        (
            "Medic Ren",
            "Use the aid kit and escort the scout.",
            "Use kit and escort",
        ),
        ("Warden Vale", "Give me the trial permit.", "Ask for permit"),
        ("Professor", "Tell me Earth tactics.", "Ask Earth tactics"),
        ("Professor", "Register my entry.", "Register entry"),
    ]:
        terminal.scene(scene)
        conversation(terminal, text, meaning)
    terminal.journal()
    terminal.expect("Items: permit, supply_pack")
    for flag in [
        "Scout at camp",
        "Exact tag clue copied",
        "Dry route marked",
        "Trial permit received",
        "One supply pack reserved",
        "Tactics notes ready",
        "Scout duty complete",
        "Trial entry registered",
    ]:
        terminal.expect(f"[done] {flag}")


def test_resize_and_menu_quit(terminal):
    def resize(rows, columns):
        terminal.screen.resize(lines=rows, columns=columns)
        fcntl.ioctl(
            terminal.master,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", rows, columns, 0, 0),
        )
        os.kill(terminal.process.pid, signal.SIGWINCH)
        terminal.pump()
        terminal.record(f"resize {columns}x{rows}")

    resize(15, 55)
    terminal.expect("Resize terminal to at least 60 columns by 20 rows.")
    resize(20, 60)
    terminal.expect("CHROMATIC TEXT LAB")
    terminal.menu("Scenarios")
    terminal.expect("| scenarios")
    terminal.press("enter")
    terminal.expect("Professor | BUTTONS")
    terminal.menu("Quit")
    assert terminal.process.wait(timeout=3) == 0


@pytest.mark.skipif(
    not os.environ.get("OLLAMA_E2E_MODEL"),
    reason="Set OLLAMA_E2E_MODEL to an installed real Ollama model",
)
def test_live_ollama_generation_and_cancel(request):
    app = Terminal(
        request.node.name,
        provider="ollama",
        model=os.environ["OLLAMA_E2E_MODEL"],
    )
    try:
        app.expect("CHROMATIC TEXT LAB")
        app.type_text("Exactly one pack, not two.")
        app.press("tab")
        app.press("backspace")
        app.choose("GET DRAFT")
        app.expect("| waiting")
        app.expect("Generated PLAYER draft: ollama /", timeout=36)
        app.expect("Review the wording.")
        app.press("backspace")
        app.choose("PREVIEW")
        app.expect("EXACT TEXT:")
        app.press("escape")
        before = next(
            line
            for line in app.text.splitlines()
            if line.startswith("Draft (")
        )
        app.press("backspace")
        app.choose("GET DRAFT")
        app.expect("| waiting")
        app.press("s")
        app.expect("Cancelled. Draft retained.")
        app.expect(before)
        app.pump(1)
        app.expect(before)
        app.press("backspace")
        app.choose("GET DRAFT")
        app.expect("| waiting")
        app.press("f1")
        app.expect("| menu")
        app.expect(before)
        app.journal()
        app.expect("Items: aid_kit, crystal")
        assert "[done]" not in app.text
    finally:
        app.close()


@pytest.mark.parametrize("columns,rows", [(80, 24), (60, 20)])
def test_long_text_preview_confirm_at_supported_sizes(terminal, columns, rows):
    terminal.screen.resize(lines=rows, columns=columns)
    fcntl.ioctl(
        terminal.master,
        termios.TIOCSWINSZ,
        struct.pack("HHHH", rows, columns, 0, 0),
    )
    os.kill(terminal.process.pid, signal.SIGWINCH)
    terminal.pump()
    terminal.record(f"resize {columns}x{rows}")
    terminal.press("f1")
    terminal.press("down")
    terminal.press("enter")
    terminal.expect("| scenarios")
    terminal.press("down")
    terminal.press("enter")
    terminal.expect("Quartermaster | BUTTONS")
    terminal.press("tab")
    terminal.press("z" * 96)
    terminal.expect("Draft (96/96)")
    terminal.press("enter")
    terminal.expect("| preview")
    terminal.expect("Send exact text")
    terminal.expect("Back to editing")
    assert terminal.text.count("z") == 192
    terminal.press("enter")
    terminal.expect("| meaning")
    terminal.choose("Trade for one pack")
    terminal.expect("| confirm")
    terminal.expect("No quest changes occur until you confirm.")
    terminal.expect("Confirm meaning and apply authored outcome")
    assert terminal.text.count("z") == 192
    terminal.press("escape")
    terminal.journal()
    terminal.expect("Items: aid_kit, crystal")
