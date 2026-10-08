# SPDX-License-Identifier: GPL-3.0-or-later
"""PTY and state regressions. HTTP fixture replies are explicitly synthetic."""

from test_terminal_e2e import Terminal


def test_recorded_return_selects_one_chip():
    app = Terminal("recorded-return-one")
    try:
        app.expect("CHROMATIC TEXT LAB")
        app.press("down", 2)
        app.expect("> one")
        app.press("enter")
        app.expect("Draft (3/96): |one|")
        app.expect("| editor")
    finally:
        app.close()


def test_ollama_send_starts_npc_reply_without_meaning_picker():
    app = Terminal(
        "ollama-send-contract",
        provider="ollama",
        model="SYNTHETIC-unavailable",
    )
    try:
        app.expect("CHROMATIC TEXT LAB")
        app.type_text("Hello Quartermaster.")
        app.press("enter")
        app.expect("| preview")
        app.expect("Send to Quartermaster via Ollama")
    finally:
        app.close()


import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX PTY required"
)

from chromatic_demo.terminal_state import TerminalState, load_world


@pytest.fixture
def synthetic_ollama():
    """Real HTTP transport with explicitly synthetic NPC prose, no model inference."""
    requests = []
    replies = [
        "SYNTHETIC NPC: Welcome, traveler.",
        "SYNTHETIC NPC: I remember your greeting.",
    ]
    delay = [0]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
            )
            text = replies.pop(0)
            time.sleep(delay[0])
            self.send_response(500 if text is None else 200)
            self.end_headers()
            try:
                self.wfile.write(
                    json.dumps({"done": True, "response": text}).encode()
                )
            except BrokenPipeError:
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"http://127.0.0.1:{server.server_port}",
            requests,
            replies,
            delay,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_transport_two_turn_npc_chat_and_separate_quest_actions(
    synthetic_ollama,
):
    url, requests, _, _ = synthetic_ollama
    app = Terminal(
        "synthetic-npc-two-turn", "ollama", "SYNTHETIC-fixture", ollama_url=url
    )
    try:
        app.expect("CHROMATIC TEXT LAB")
        app.press("down", 2)
        app.press("enter")
        app.expect("|one|")
        app.press("backspace")
        app.press("right")
        app.press("enter")
        app.expect("| preview")
        app.press("enter")
        app.expect("SYNTHETIC NPC: Welcome, traveler.")
        assert "KEYBOARD: letters type" not in app.text
        app.expect("> Continue conversation")
        app.expect("Quest actions (scripted)")
        assert "| meaning" not in app.text
        assert "NPC: Quartermaster" in requests[0]["prompt"]
        assert "Player message: one\n" in requests[0]["prompt"]
        assert "PLAYER'S outgoing" not in requests[0]["prompt"]
        app.press("enter")
        app.expect("Draft (0/96): ||")
        app.expect("Last NPC reply: SYNTHETIC NPC: Welcome, traveler.")
        app.type_text("Remember my greeting?")
        app.press("enter")
        app.press("enter")
        app.expect("SYNTHETIC NPC: I remember your greeting.")
        assert (
            "Player: one\nNPC: SYNTHETIC NPC: Welcome, traveler."
            in requests[1]["prompt"]
        )
        app.choose("Quest actions (scripted)")
        app.expect("SCRIPTED QUEST ACTIONS")
        app.choose("Trade for one pack")
        app.expect("No quest changes occur until you confirm.")
        app.press("enter")
        app.expect("One crystal for one supply pack, agreed.")
        app.journal()
        app.expect("Items: aid_kit, supply_pack")
        app.expect("[done] One supply pack reserved")
    finally:
        app.close()


@pytest.mark.parametrize("failure", ["error", "cancel", "empty"])
def test_transport_failure_retains_draft_and_allows_retry(
    synthetic_ollama, failure
):
    url, requests, replies, delay = synthetic_ollama
    replies[:] = [
        None
        if failure == "error"
        else ""
        if failure == "empty"
        else "SYNTHETIC delayed"
    ]
    delay[0] = 2 if failure == "cancel" else 0
    app = Terminal(
        "synthetic-failure-" + failure,
        "ollama",
        "SYNTHETIC-fixture",
        ollama_url=url,
    )
    try:
        app.expect("CHROMATIC TEXT LAB")
        app.type_text("Keep my crystal.")
        app.press("enter")
        app.press("enter")
        if failure == "cancel":
            app.expect("| waiting")
            app.press("enter")
            app.expect("| waiting")
            app.press("s")
            app.expect("Cancelled. Draft retained.")
            app.pump(2.1)
        else:
            app.expect("Draft retained. PREVIEW to retry.", timeout=5)
        app.expect("| editor")
        app.expect("|Keep my crystal.|")
        app.journal()
        app.expect("Items: aid_kit, crystal")
        assert "[done]" not in app.text
        delay[0] = 0
        replies[:] = ["SYNTHETIC NPC: Retry succeeded."]
        app.press("enter")
        app.expect("| editor")
        app.press("enter")
        app.expect("| preview")
        app.press("enter")
        app.expect("SYNTHETIC NPC: Retry succeeded.")
        assert "Player message: Keep my crystal.\n" in requests[-1]["prompt"]
        assert "SYNTHETIC delayed" not in requests[-1]["prompt"]
        app.journal()
        app.expect("Items: aid_kit, crystal")
        assert "[done]" not in app.text
    finally:
        app.close()


def test_npc_history_context_guards_and_reset():
    state = TerminalState(load_world(), provider="ollama", model="SYNTHETIC")
    state.set_draft("My name is Cedar.")
    state.begin_request("reply")
    token = state.pending
    assert state.accept_result(token, "Welcome Cedar. I grant a pack!")
    assert (state.flags, state.inventory) == (0, 3)
    assert state.conversations[1] == [
        ("My name is Cedar.", "Welcome Cedar. I grant a pack!")
    ]
    assert "Player: My name is Cedar." in state.dialogue_context()
    state.change_scene(2)
    assert "Cedar" not in state.dialogue_context()
    assert (
        "One crystal for one supply pack, agreed."
        not in state.dialogue_context()
    )
    state.change_scene(1)
    for i in range(20):
        state.conversations[1].append(("x" * 96, str(i) + "y" * 310))
    context = state.dialogue_context()
    assert len(context) <= 2048
    assert "19" + "y" * 310 in context
    assert "Current game facts:" in context
    assert "Player: My name is Cedar." not in context
    state.phase, state.cursor = "reset", 1
    state.handle("a")
    assert state.conversations == {}


@pytest.mark.parametrize(
    "change",
    [
        "cancel",
        "error",
        "timeout",
        "empty",
        "draft",
        "npc",
        "method",
        "provider",
        "model",
        "operation",
        "reset",
    ],
)
def test_failed_or_stale_reply_never_appends_history(change):
    state = TerminalState(load_world(), provider="ollama", model="SYNTHETIC")
    state.set_draft("Keep my crystal.")
    state.begin_request("reply")
    token = state.pending
    if change == "cancel":
        state.cancel()
    elif change == "draft":
        state.set_draft("Changed text.")
    elif change == "npc":
        state.change_scene(2)
    elif change == "method":
        state.change_method(3)
    elif change == "provider":
        state.provider = "authored"
    elif change == "model":
        state.model = "SYNTHETIC-other"
    elif change == "operation":
        state.begin_request("compose")
    elif change == "reset":
        state.phase, state.cursor = "reset", 1
        state.handle("a")
    assert not state.accept_result(
        token,
        "" if change == "empty" else "SYNTHETIC reply",
        "Provider timed out."
        if change == "timeout"
        else "failure"
        if change == "error"
        else None,
    )
    assert not state.conversations
    assert (state.flags, state.inventory) == (0, 3)
    if change not in ("draft", "reset"):
        assert state.draft == "Keep my crystal."


def test_long_npc_reply_readable_at_minimum_size(synthetic_ollama):
    import fcntl
    import os
    import signal
    import struct
    import termios

    url, _, replies, _ = synthetic_ollama
    reply = " ".join(f"word{i:02}" for i in range(44)) + " final-marker"
    assert len(reply) <= 320
    replies[:] = [reply]
    app = Terminal(
        "synthetic-long-npc",
        "ollama",
        "SYNTHETIC-" + "model" * 22,
        ollama_url=url,
    )
    try:
        app.expect("CHROMATIC TEXT LAB")
        app.screen.resize(lines=20, columns=60)
        fcntl.ioctl(
            app.master, termios.TIOCSWINSZ, struct.pack("HHHH", 20, 60, 0, 0)
        )
        os.kill(app.process.pid, signal.SIGWINCH)
        app.pump()
        app.press("tab")
        app.press("x" * 96)
        app.expect("Draft (96/96)")
        app.press("enter")
        app.press("enter")
        app.expect("NPC reply via Ollama /")
        app.expect("Page 1/")
        app.expect("Left/Right pages")
        seen = app.text
        app.press("right")
        app.expect("Page 2/")
        seen += "\n" + app.text
        for word in reply.split():
            assert word in seen
        app.expect("Continue conversation")
        app.expect("Quest actions (scripted)")
        assert "Left/Right pages" in app.text
    finally:
        app.close()


def test_npc_timeout_stops_owned_worker_and_preserves_draft():
    from unittest.mock import Mock

    from chromatic_demo.terminal import DraftWorker

    state = TerminalState(load_world(), provider="ollama", model="SYNTHETIC")
    state.set_draft("Keep my crystal.")
    state.begin_request("reply")
    worker = DraftWorker()
    worker.token = state.pending
    worker.process = Mock()
    worker.connection = Mock()
    worker.connection.poll.return_value = False
    worker.process.is_alive.return_value = True
    worker.started = time.monotonic() - 36
    worker.poll(state)
    assert worker.process is None
    assert state.pending is None
    assert state.phase == "editor"
    assert "timed out" in state.message
    assert state.draft == "Keep my crystal."
    assert not state.conversations


@pytest.mark.skipif(
    not __import__("os").environ.get("OLLAMA_E2E_MODEL"),
    reason="Opt-in real Ollama NPC reply",
)
def test_live_ollama_npc_reply_and_followup(request):
    import os

    app = Terminal(request.node.name, "ollama", os.environ["OLLAMA_E2E_MODEL"])
    try:
        app.expect("CHROMATIC TEXT LAB")
        app.type_text("Hello, my name is Cedar. Who are you?")
        app.press("enter")
        app.press("enter")
        app.expect("| npc_reply", timeout=36)
        app.expect("NPC reply via Ollama /")
        app.expect("> Continue conversation")
        lines = app.text.splitlines()
        start = next(
            i
            for i, line in enumerate(lines)
            if line.startswith("Quartermaster: ")
        )
        end = next(
            i
            for i in range(start + 1, len(lines))
            if lines[i].startswith("Page ")
        )
        answer = " ".join(lines[start:end]).removeprefix("Quartermaster: ")
        assert answer != "Hello, my name is Cedar. Who are you?", (
            "NPC echoed the player's message"
        )
        assert "quartermaster" in answer.lower(), (
            f"NPC did not introduce itself: {answer}"
        )
        app.press("enter")
        app.expect("Draft (0/96): ||")
        app.press("What name did I just give you?")
        app.press("enter")
        app.press("enter")
        app.expect("| npc_reply", timeout=36)
        app.expect("Cedar")
        app.journal()
        app.expect("Items: aid_kit, crystal")
        assert "[done]" not in app.text
    finally:
        app.close()


def test_transport_npc_switch_isolates_history_and_model_cannot_grant_items(
    synthetic_ollama,
):
    url, requests, replies, _ = synthetic_ollama
    replies[:] = [
        "SYNTHETIC: I gave you a permit and spent the crystal.",
        "SYNTHETIC: I am Iona.",
    ]
    app = Terminal(
        "synthetic-isolation", "ollama", "SYNTHETIC-fixture", ollama_url=url
    )
    try:
        app.expect("CHROMATIC TEXT LAB")
        app.type_text("My name is Cedar.")
        app.press("enter")
        app.press("enter")
        app.expect("I gave you a permit and spent the crystal.")
        app.journal()
        app.expect("Items: aid_kit, crystal")
        assert "[done]" not in app.text
        app.press("enter")
        app.scene("Tracker Iona")
        app.press("backspace", len("My name is Cedar."))
        app.press("Hello Iona.")
        app.press("enter")
        app.press("enter")
        app.expect("SYNTHETIC: I am Iona.")
        assert "NPC: Tracker Iona" in requests[1]["prompt"]
        assert "Cedar" not in requests[1]["prompt"]
        assert "spent the crystal" not in requests[1]["prompt"]
        assert '"inventory": ["aid_kit", "crystal"]' in requests[1]["prompt"]
    finally:
        app.close()
