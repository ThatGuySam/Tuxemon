# SPDX-License-Identifier: GPL-3.0-or-later
"""Conversation overlay on the real Tuxemon world, never a separate loop."""

from __future__ import annotations

import textwrap
import threading

import pygame

from tuxemon.custom_game.composer import METHODS
from tuxemon.custom_game.runtime import Ollama
from tuxemon.platform.const import buttons, events, intentions
from tuxemon.state.state import State


class CustomConversationState(State):
    name = "CustomConversationState"
    transparent = True

    def __init__(self, client, **kwargs):
        super().__init__(client, **kwargs)
        self.model = client.custom_scenario
        self.results = self.model.results
        self.font = pygame.font.Font(None, max(16, self.rect.height // 30))
        self.line_height = self.font.get_linesize()
        self.saved_handlers = []
        self.saved_middleware = []
        world = client.state_manager.get_state_by_name("WorldState")
        for attr, priority in (
            ("camera_mw", 5),
            ("movement_mw", 10),
            ("devtools_mw", 20),
            ("command_mw", 30),
        ):
            middleware = getattr(world, attr)
            if any(
                m is middleware
                for _, m in client.event_manager.middleware.values()
            ):
                self.saved_middleware.append((middleware, priority))
                client.event_manager.remove_middleware(middleware)
        from tuxemon.platform.platform_pygame.events import PygameKeyboardInput

        for handler in client.input_manager.event_queue.get_input_handlers():
            if isinstance(handler, PygameKeyboardInput):
                self.saved_handlers.append((handler, dict(handler.event_map)))
        self.configure_keyboard()

    def configure_keyboard(self):
        for handler, original in self.saved_handlers:
            mapping = {
                **original,
                pygame.K_TAB: buttons.SELECT,
                pygame.K_F1: buttons.START,
                pygame.K_ESCAPE: buttons.B,
            }
            if self.model.keyboard and self.model.phase == "editor":
                # Normal Shift must type capitals, never trigger the game's B.
                mapping.pop(pygame.K_LSHIFT, None)
                mapping.pop(pygame.K_RSHIFT, None)
            if mapping != handler.event_map:
                handler.reload_mapping(mapping)

    def process_event(self, event):
        if not event.pressed:
            return None
        model = self.model
        if event.button == events.UNICODE:
            if model.keyboard and model.phase == "editor":
                model.set_draft(model.draft + str(event.value))
            return None
        if event.button == events.BACKSPACE:
            if model.phase == "editor":
                model.set_draft(model.draft[:-1])
            return None
        actions = {
            buttons.A: "a",
            intentions.SELECT: "a",
            intentions.INTERACT: "a",
            buttons.B: "b",
            buttons.BACK: "tab",
            intentions.MENU_CANCEL: "b",
            buttons.UP: "up",
            buttons.DOWN: "down",
            buttons.LEFT: "left",
            buttons.RIGHT: "right",
            buttons.START: "start",
            buttons.SELECT: "tab",
        }
        action = actions.get(event.button)
        if action:
            model.handle(action)
            if model.quit:
                model.cancel()
                model.npc_drafts[model.npc] = model.draft
                self.client.pop_state(self)
                return None
            self.configure_keyboard()
        return None

    def update(self, dt):
        super().update(dt)
        self.configure_keyboard()
        while not self.results.empty():
            token, text, error = self.results.get_nowait()
            self.model.accept_result(token, text=text, error=error)
        token = self.model.pending
        if token is None or token == self.model.request:
            return
        if self.model.worker and self.model.worker.is_alive():
            self.model.accept_result(
                token,
                error="Previous cancelled request is still finishing. Retry shortly.",
            )
            return
        self.model.request = token
        npc = self.model.scene["name"]
        results = self.results

        def request_reply():
            try:
                text = Ollama(token.endpoint, token.model).reply(npc, token)
                results.put((token, text, None))
            except Exception as error:
                results.put(
                    (
                        token,
                        None,
                        f"Ollama unavailable: {type(error).__name__}: {str(error)[:160]}",
                    )
                )

        # Cancellation invalidates the snapshot immediately; bounded I/O finishes
        # in the background. A daemon cannot keep the game alive on exit.
        self.model.worker = threading.Thread(target=request_reply, daemon=True)
        self.model.worker.start()

    def shutdown(self):
        self.model.cancel()
        for handler, mapping in self.saved_handlers:
            handler.reload_mapping(mapping)
        for middleware, priority in self.saved_middleware:
            self.client.event_manager.add_middleware(
                middleware, priority=priority
            )
        super().shutdown()

    def draw(self, surface):
        model = self.model
        panel = self.rect.inflate(-12, -12)
        pygame.draw.rect(surface, (15, 23, 35), panel, border_radius=6)
        pygame.draw.rect(surface, (101, 184, 170), panel, 2, border_radius=6)
        x, y = panel.x + 12, panel.y + 10
        width = panel.width - 24
        chars = max(20, width // self.font.size("M")[0])

        def line(text, color=(232, 237, 242)):
            nonlocal y
            surface.blit(self.font.render(text, True, color), (x, y))
            y += self.line_height

        def wrap(text):
            return textwrap.wrap(
                text, chars, replace_whitespace=False, drop_whitespace=False
            ) or [""]

        method = dict(METHODS)[model.method]
        line(
            f"{model.scene['name']} | {model.phase.replace('_', ' ')}",
            (125, 220, 198),
        )
        line(
            f"{method} | {'KEYBOARD' if model.keyboard else 'D-pad'} | {len(model.draft)}/96"
        )
        label = (
            "Ollama NPC reply"
            if model.phase == "npc_reply"
            else "Authored game / status"
        )
        if model.phase == "npc_reply":
            label += " via " + (model.model or "unconfigured")
        line(label, (180, 194, 215))
        message = model.message
        if model.phase == "journal":
            message = model.dialogue_context()
        elif model.phase == "settings":
            message = (
                f"Ollama endpoint: {model.endpoint or 'NOT CONFIGURED'}. "
                f"Model: {model.model or 'NOT CONFIGURED'}. "
                "Set TUXEMON_OLLAMA_URL and TUXEMON_OLLAMA_MODEL before launch. "
                "No model fallback; no account credentials."
            )
        rows = wrap(message)
        model.reply_pages = max(1, (len(rows) + 3) // 4)
        model.reply_page %= model.reply_pages
        for row in rows[model.reply_page * 4 : model.reply_page * 4 + 4]:
            line(row)
        y = panel.y + 10 + self.line_height * 7
        line(
            f"Text page {model.reply_page + 1}/{model.reply_pages} | Left/Right scrolls replies"
        )
        line(
            "EXACT OUTGOING TEXT "
            + (
                "(review before Send)"
                if model.phase == "preview"
                else "(draft)"
            ),
            (245, 215, 140),
        )
        # repr makes spaces, quotes and punctuation reviewable without silently
        # normalizing the outgoing message. The HTTP adapter sends draft verbatim.
        draft_rows = wrap(repr(model.draft))
        for row in draft_rows:
            line(row, (245, 215, 140))
        y = max(y, panel.y + 10 + self.line_height * 12)
        options = model.options()
        model.cursor %= len(options)
        capacity = max(3, (panel.bottom - y) // self.line_height - 4)
        start = max(
            0, min(model.cursor - capacity // 2, len(options) - capacity)
        )
        for index in range(start, min(len(options), start + capacity)):
            prefix = "> " if index == model.cursor else "  "
            text = f"{prefix}{index + 1}. {options[index]}"
            line(
                text[:chars],
                (125, 220, 198) if index == model.cursor else (232, 237, 242),
            )
        y = panel.bottom - self.line_height * 3 - 5
        back = (
            "Esc/B back"
            if model.keyboard and model.phase == "editor"
            else "Esc/Shift/B back"
        )
        line(f"D-pad/arrows | Return/A activate | {back}")
        line("F1/Start menu | Tab/Select keyboard | Backspace delete")
        line("PREVIEW > Send | Quest actions confirm separately")
