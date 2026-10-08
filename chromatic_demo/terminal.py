# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the Mac text adaptation of the Chromatic input playground."""

import argparse
import curses
import multiprocessing
import textwrap
import time

from .playground_bridge import COMPOSE, Broker, Turn
from .terminal_state import METHODS, TerminalState, load_world


def generate(connection, world, token):
    try:
        if token.operation == "reply":
            from .providers import OllamaProvider

            text = OllamaProvider(token.model, token.endpoint).reply(
                world["npcs"][token.npc]["name"], token.text, token.context
            )
        else:
            turn = Turn(
                token.sequence,
                token.context_revision,
                token.draft_revision,
                token.npc,
                token.method,
                COMPOSE,
                token.text,
            )
            text = (
                Broker(
                    world,
                    provider=token.provider,
                    model=token.model,
                    ollama_url=token.endpoint,
                )
                .run(turn)
                .text
            )
        connection.send((token, text, None))
    except Exception as error:
        connection.send((token, None, f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


class DraftWorker:
    def __init__(self):
        self.process = self.connection = self.token = None
        self.started = 0

    def stop(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=1)
            self.process.close()
        if self.connection is not None:
            self.connection.close()
        self.process = self.connection = self.token = None

    def poll(self, state):
        if self.token is not None and self.token != state.pending:
            self.stop()
        if state.pending is not None and self.process is None:
            context = multiprocessing.get_context("spawn")
            self.connection, child = context.Pipe(duplex=False)
            self.token = state.pending
            self.process = context.Process(
                target=generate,
                args=(child, state.world, self.token),
            )
            self.process.start()
            child.close()
            self.started = time.monotonic()
        if self.process is None:
            return
        if self.connection.poll():
            try:
                token, text, error = self.connection.recv()
            except EOFError:
                token, text, error = (
                    self.token,
                    None,
                    "Provider worker disconnected.",
                )
            state.accept_result(token, text, error)
            self.stop()
        elif time.monotonic() - self.started > 35:
            state.accept_result(self.token, error="Provider timed out.")
            self.stop()
        elif not self.process.is_alive():
            state.accept_result(
                self.token, error="Provider worker exited without a result."
            )
            self.stop()


def key_event(state, key):
    if key == "\x03" or key == "\x11":
        state.handle("quit")
        return
    if key == "\t":
        state.handle("tab")
        return
    if key == curses.KEY_F1:
        if state.phase == "waiting":
            state.cancel()
        state.handle("start")
        return
    if key == "\x1b":
        state.handle("b")
        return
    if state.keyboard and state.phase == "editor":
        if key in ("\n", "\r", curses.KEY_ENTER):
            if state.draft.strip():
                state.phase, state.cursor = "preview", 0
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            state.set_draft(state.draft[:-1])
        elif isinstance(key, str):
            state.set_draft(state.draft + key)
        return
    mapping = {
        curses.KEY_UP: "up",
        curses.KEY_DOWN: "down",
        curses.KEY_LEFT: "left",
        curses.KEY_RIGHT: "right",
        "a": "a",
        "s": "b",
        "A": "a",
        "S": "b",
        "\n": "a",
        "\r": "a",
        curses.KEY_ENTER: "a",
        curses.KEY_BACKSPACE: "select",
        "\x7f": "select",
        "\b": "select",
    }
    if key in mapping:
        state.handle(mapping[key])


def render(screen, state):
    screen.erase()
    height, width = screen.getmaxyx()
    if height < 20 or width < 60:
        try:
            screen.addnstr(
                0,
                0,
                "Resize terminal to at least 60 columns by 20 rows. Ctrl-C quits.",
                max(0, width - 1),
            )
        except curses.error:
            pass
        screen.refresh()
        return
    lines = [
        "CHROMATIC TEXT LAB | Mac adaptation, not ROM execution",
        f"{dict(METHODS)[state.method]} | {state.provider} / {state.model or 'no model'} | {state.phase}",
        (
            "Typing: letters insert; Esc=back F1=menu Tab=buttons"
            if state.phase == "editor" and state.keyboard
            else "Arrows=D-pad a=A s/Esc=B F1=menu Tab=typing"
        ),
        (
            "Enter=preview; Backspace=delete; Tab=buttons"
            if state.phase == "editor" and state.keyboard
            else "Enter/a=choose; F1=menu; Backspace=actions"
            if state.phase == "editor"
            else "s/Esc=cancel; draft retained"
            if state.phase == "waiting"
            else "Enter/a=choose; s/Esc=back; F1=menu"
        ),
        f"{state.scene['name']} | "
        + (
            "KEYBOARD: letters type; Enter previews"
            if state.phase == "editor" and state.keyboard
            else "BUTTONS"
        ),
    ]
    if state.phase == "editor":
        lines += [f"You are talking to {state.scene['name']}."]
        history = state.conversations.get(state.npc, [])
        lines += textwrap.wrap(
            "Last NPC reply: " + history[-1][1]
            if history
            else state.scene["opening"],
            width - 2,
        )[:3]
    if state.phase not in ("journal", "settings", "npc_reply"):
        lines += textwrap.wrap(
            f"Draft ({len(state.draft)}/96): |{state.draft}|",
            width - 2,
            replace_whitespace=False,
            drop_whitespace=False,
        )
    if state.phase not in (
        "journal",
        "settings",
    ) and state.provenance.startswith("Generated"):
        lines += textwrap.wrap(state.provenance, width - 2)
    if state.phase in ("preview", "meaning", "confirm"):
        lines += textwrap.wrap(
            "EXACT TEXT: |"
            + (
                state.sent
                if state.phase in ("meaning", "confirm")
                else state.draft
            )
            + "|",
            width - 2,
            replace_whitespace=False,
            drop_whitespace=False,
        )
    if state.phase == "meaning" and state.provider == "ollama":
        lines += ["SCRIPTED QUEST ACTIONS. Choose then confirm."]
    if state.phase == "confirm":
        meaning = (
            state.scene["replies"][state.meaning]
            if state.meaning < len(state.scene["replies"])
            else None
        )
        lines += textwrap.wrap(
            "Chosen meaning: "
            + (meaning["label_description"] if meaning else "Unresolved"),
            width - 2,
        )
        lines += ["No quest changes occur until you confirm."]
    if state.phase == "journal":
        lines += [
            "Items: "
            + ", ".join(
                k
                for k, v in state.world["items"].items()
                if state.inventory & v
            )
        ]
        lines += [
            ("[done] " if state.flags & int(bit) else "[ ] ") + label
            for bit, label in state.world["journal"]["flag_labels"].items()
        ]
    elif state.phase == "settings":
        lines += [
            "Ollama Send asks the NPC. GET DRAFT rewrites you.",
            "--provider authored",
            "--provider ollama --model NAME",
            "--provider chatgpt --model SLUG",
            "ChatGPT setup: python -m chromatic_demo.auth login",
            "Then: python -m chromatic_demo.auth models",
            "No API key fallback. Model drafts cannot change quests.",
        ]
    elif state.phase == "editor" and state.method == 5 and not state.spelling:
        lines += [
            "URDL codes: U=a ... L=d; UU=e ... LL=t; UUU=u ... UDR='",
            "A commits trace. B undoes; empty B opens actions.",
        ]
    if state.phase == "npc_reply":
        lines = lines[:5]
        lines += textwrap.wrap(
            f"NPC reply via Ollama / {state.model}", width - 2
        )
        content = textwrap.wrap("You: " + state.sent, width - 2)
        content += textwrap.wrap(
            state.scene["name"] + ": " + state.message, width - 2
        )
        capacity = max(1, height - len(lines) - 6)
        state.reply_pages = max(1, (len(content) + capacity - 1) // capacity)
        state.reply_page = min(state.reply_page, state.reply_pages - 1)
        start = state.reply_page * capacity
        lines += content[start : start + capacity]
        lines += [
            f"Page {state.reply_page + 1}/{state.reply_pages}; Left/Right pages; Up/Down options"
        ]
    elif state.phase == "reply":
        lines += textwrap.wrap(state.message, width - 2)
    elif state.phase not in ("journal", "settings"):
        lines += textwrap.wrap(state.message, width - 2)[:2]
    if state.phase != "waiting" and not (
        state.keyboard and state.phase == "editor"
    ):
        options = state.options()
        lines = lines[: height - 5]
        capacity = max(2, height - len(lines) - 2)
        start = max(
            0, min(state.cursor - capacity // 2, len(options) - capacity)
        )
        lines += [
            ("> " if i == state.cursor else "  ") + options[i]
            for i in range(start, min(len(options), start + capacity))
        ]
        if len(options) > capacity:
            lines += [
                f"Options {start + 1}-{min(len(options), start + capacity)} of {len(options)}; arrows scroll"
            ]
    for row, line in enumerate(lines[: height - 1]):
        try:
            screen.addnstr(
                row,
                0,
                line,
                width - 1,
                curses.A_REVERSE if line.startswith("> ") else curses.A_NORMAL,
            )
        except curses.error:
            pass
    screen.refresh()


def run(screen, state):
    screen.keypad(True)
    screen.timeout(100)
    curses.curs_set(0)
    worker = DraftWorker()
    try:
        while not state.quit:
            worker.poll(state)
            render(screen, state)
            try:
                key_event(state, screen.get_wch())
            except curses.error:
                pass
    finally:
        state.cancel()
        worker.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=("authored", "ollama", "chatgpt"),
        default="authored",
    )
    parser.add_argument("--model")
    parser.add_argument("--scenario", type=int, choices=range(5), default=1)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args(argv)
    if args.provider == "ollama":
        from .providers import OllamaProvider

        try:
            OllamaProvider(args.model, args.ollama_url)
        except ValueError as error:
            parser.error(str(error))
    if args.provider != "authored" and not args.model:
        parser.error(
            "Select an explicit installed Ollama model or ChatGPT account catalog slug with --model"
        )
    state = TerminalState(
        load_world(),
        npc=args.scenario,
        provider=args.provider,
        model=args.model,
        endpoint=args.ollama_url,
    )
    try:
        curses.wrapper(run, state)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
