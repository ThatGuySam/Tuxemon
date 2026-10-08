# SPDX-License-Identifier: GPL-3.0-or-later
"""Behavior checks; model responses below are synthetic protocol fixtures."""

import io
import json
from unittest.mock import Mock, patch

import pytest

from chromatic_demo.playground_bridge import COMPOSE, Broker, Turn
from chromatic_demo.providers import completed_text
from chromatic_demo.terminal import DraftWorker, key_event
from chromatic_demo.terminal_state import (
    ALPHABET,
    METHODS,
    TREE,
    TerminalState,
    load_world,
)


@pytest.fixture
def state():
    return TerminalState(load_world())


def choose(state, name):
    state.cursor = state.options().index(name)
    state.handle("a")


def commit(state, label):
    reply = next(r for r in state.scene["replies"] if r["label"] == label)
    state.set_draft(reply["utterance"])
    state.phase = "editor"
    choose(state, "PREVIEW")
    state.handle("a")
    state.cursor = state.scene["replies"].index(reply)
    state.handle("a")
    state.handle("a")


def test_all_nine_methods_produce_text(state):
    for method, _ in METHODS:
        state.set_draft("")
        state.change_method(method)
        if method == 0:
            for _ in range(3):
                state.handle("a")
        elif method == 2:
            state.set_draft("tmc")
            state.handle("a")
        elif method == 5:
            state.handle("up")
            state.handle("a")
        elif method == 6:
            for _ in range(3):
                state.handle("a")
        elif method in (4, 7):
            state.handle("a")
            state.handle("a")
        elif method == 8:
            state.handle("a")
            key_event(state, "h")
            key_event(state, "\t")
        else:
            state.handle("a")
        assert state.draft, method
        assert (state.flags, state.inventory) == (0, 3)


def test_full_keyboard_keeps_draft_and_enter_only_previews(state):
    state.set_draft("not ")
    key_event(state, "\t")
    key_event(state, "a")
    key_event(state, "s")
    assert state.draft == "not as"
    key_event(state, "\t")
    assert not state.keyboard and state.draft == "not as"
    choose(state, "HOST KEYBOARD")
    key_event(state, "\n")
    assert state.phase == "preview" and state.flags == 0 and not state.sent


def test_invalid_text_keeps_existing_draft(state):
    state.set_draft("original")
    for text in ("x" * 97, "Lumé", "a\nb", "\t", "\x00"):
        assert not state.set_draft(text)
        assert state.draft == "original"
    assert state.set_draft("x" * 96)


def test_initials_only_word_starts(state):
    state.change_method(2)
    state.set_draft("tmc")
    assert state.initials_match(0)
    state.set_draft("trade")
    assert not state.initials_match(0)


def test_grid_pages_completion_and_b_return(state):
    state.change_method(1)
    choose(state, "SPELL")
    state.set_draft("tr")
    choose(state, "COMPLETE")
    assert state.draft == "trade"
    for _ in range(4):
        for index in range(len(state.body()) - 2):
            state.activate_body(index)
            assert all(32 <= ord(c) <= 126 for c in state.draft)
            state.set_draft("")
        choose(state, "PAGE")
    state.handle("b")
    assert not state.spelling


def test_all_edgewrite_codes_and_cancel(state):
    state.change_method(5)
    for index, expected in enumerate(ALPHABET):
        count, value = (
            (1, index)
            if index < 4
            else (2, index - 4)
            if index < 20
            else (3, index - 20)
        )
        directions = []
        for _ in range(count):
            directions.insert(0, ("up", "right", "down", "left")[value % 4])
            value //= 4
        state.set_draft("")
        for action in directions:
            state.handle(action)
        state.handle("a")
        assert state.draft == expected
    state.handle("left")
    state.handle("b")
    assert state.trace == ""
    state.handle("b")
    assert state.cursor == 1


def test_every_tree_character_is_reachable(state):
    state.change_method(6)
    for character in TREE:
        state.set_draft("")
        state.branch = TREE
        while not state.draft:
            state.cursor = next(
                i for i, group in enumerate(state.body()) if character in group
            )
            state.handle("a")
        assert state.draft == character


def test_radial_last_group_and_grouped_last_character(state):
    state.change_method(7)
    state.handle("left")
    state.handle("a")
    assert "'" in state.body()
    choose(state, "'")
    assert state.draft == "'"
    state.change_method(4)
    state.cursor = 5
    state.handle("a")
    state.cursor = 4
    state.handle("a")
    assert state.draft == "''"


def test_effects_only_after_confirmation_and_guarded_repeat(state):
    state.set_draft("Trade one crystal.")
    choose(state, "PREVIEW")
    state.handle("a")
    state.handle("a")
    assert state.phase == "confirm" and (state.flags, state.inventory) == (
        0,
        3,
    )
    state.handle("a")
    assert (state.flags, state.inventory) == (16, 9)
    commit(state, "buy_one")
    assert (state.flags, state.inventory) == (16, 9)
    assert "different quest state" in state.message


def test_refusal_and_complete_quest(state):
    commit(state, "refuse_trade")
    assert (state.flags, state.inventory) == (0, 3)
    for npc, label in [
        (1, "buy_one"),
        (2, "correct_name"),
        (2, "safe_route"),
        (3, "rescue_scout"),
        (4, "get_permit"),
        (0, "earth_plan"),
        (0, "epilogue"),
    ]:
        state.change_scene(npc)
        commit(state, label)
    assert state.flags & 128
    assert state.inventory == 12


def test_cancellation_stale_results_and_errors_preserve_draft(state):
    state.provider, state.model = "ollama", "SYNTHETIC-model"
    state.set_draft("not two")
    state.begin_request()
    token = state.pending
    state.handle("b")
    assert not state.accept_result(token, "two")
    assert state.draft == "not two"
    state.begin_request()
    assert not state.accept_result(state.pending, "é")
    assert state.draft == "not two"
    state.begin_request()
    assert not state.accept_result(state.pending, error="timeout")
    assert state.draft == "not two"
    state.begin_request()
    token = state.pending
    state.change_scene(2)
    assert not state.accept_result(token, "stale")
    worker = DraftWorker()
    worker.process = Mock()
    worker.process.is_alive.return_value = True
    worker.stop()
    assert worker.process is None


def test_chatgpt_composes_player_not_npc(state):
    turn = Turn(1, 0, 1, 1, 1, COMPOSE, "not two")
    with patch("chromatic_demo.providers.ChatGPTProvider") as provider:
        provider.return_value.generate.return_value = "Not two packs."
        result = Broker(
            state.world, provider="chatgpt", model="SYNTHETIC-slug"
        ).run(turn)
        assert result.text == "Not two packs."
        assert (
            "PLAYER'S outgoing"
            in provider.return_value.generate.call_args.args[0]
        )
        provider.return_value.generate.return_value = "é"
        with pytest.raises(ValueError):
            Broker(
                state.world, provider="chatgpt", model="SYNTHETIC-slug"
            ).run(turn)


def test_raw_stream_retains_invalid_text_for_validator():
    events = [
        {"type": "response.output_text.delta", "delta": "é"},
        {"type": "response.completed", "response": {"status": "completed"}},
    ]
    body = b"".join(
        b"data: " + json.dumps(e).encode() + b"\n\n" for e in events
    )
    assert completed_text(io.BytesIO(body), raw=True) == "é"
    assert completed_text(io.BytesIO(body)) == "?"


class Screen:
    def __init__(self, height=20, width=60):
        self.height, self.width, self.lines = height, width, {}

    def erase(self):
        self.lines.clear()

    def getmaxyx(self):
        return self.height, self.width

    def addnstr(self, row, column, text, count, *args):
        self.lines[row] = text[:count]

    def refresh(self):
        pass


def test_minimum_terminal_displays_exact_preview_and_actions(state):
    from chromatic_demo.terminal import render

    state.set_draft(" " + "z" * 94 + " ")
    state.phase = "preview"
    screen = Screen()
    render(screen, state)
    rendered = "\n".join(screen.lines.values())
    assert "Send exact text" in rendered
    assert "Back to editing" in rendered
    assert rendered.count("z") == 188
    assert "| " in rendered and " |" in rendered


def test_minimum_terminal_displays_all_journal_flags(state):
    from chromatic_demo.terminal import render

    state.set_draft("z" * 96)
    state.provenance = "Generated PLAYER draft: ollama / SYNTHETIC-model"
    state.phase = "journal"
    screen = Screen()
    render(screen, state)
    rendered = "\n".join(screen.lines.values())
    for label in state.world["journal"]["flag_labels"].values():
        assert label in rendered
    assert "Back to editing" in rendered


def test_intent_composer_every_combination_fits(state):
    for npc in range(5):
        state.change_scene(npc)
        state.change_method(0)
        for goal in range(3):
            for topic in range(6):
                for stance in range(3):
                    state.set_draft("")
                    state.step = 0
                    state.activate_body(goal)
                    state.activate_body(topic)
                    state.activate_body(stance)
                    assert state.draft and len(state.draft) <= 96


def test_radial_b_opens_actions(state):
    state.change_method(7)
    state.handle("b")
    assert state.phase == "editor" and state.cursor == len(state.body())


def test_cancellation_terminates_owned_worker():
    import multiprocessing
    import os
    import time

    worker = DraftWorker()
    worker.process = multiprocessing.get_context("spawn").Process(
        target=time.sleep, args=(30,)
    )
    worker.process.start()
    pid = worker.process.pid
    worker.stop()
    assert worker.process is None
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
