# SPDX-License-Identifier: GPL-3.0-or-later
"""Scenario state and bounded Ollama protocol, independent of account auth."""

from __future__ import annotations

import json
import os
import queue
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from tuxemon.custom_game.composer import Composer, load_world
from tuxemon.custom_game.persistence import ConversationStore, NPCMemory
from tuxemon.session import local_session


class Ollama:
    def __init__(self, endpoint: str, model: str, timeout: float = 60):
        url = urlsplit(endpoint)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
            or not model
        ):
            raise ValueError(
                "Set an Ollama origin URL and explicit model name"
            )
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout

    def reply(self, npc, token):
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are {npc}. Answer the player in first person as this NPC. "
                        "Do not repeat or rewrite the player message. "
                        "Use the following authored game facts and conversation memory. "
                        "You cannot execute actions, grant items, or change quests. "
                        "Never claim unconfirmed actions happened. Reply in printable ASCII.\n"
                        + token.context
                    ),
                },
                {"role": "user", "content": token.text},
            ],
            "options": {"num_predict": 512},
        }
        request = Request(
            self.endpoint + "/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        deadline = time.monotonic() + self.timeout
        raw = bytearray()
        with urlopen(request, timeout=self.timeout) as response:
            while len(raw) <= 65536:
                if time.monotonic() > deadline:
                    raise TimeoutError("Ollama exceeded request deadline")
                chunk = response.read1(min(4096, 65537 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
        if len(raw) > 65536:
            raise ValueError("Ollama response exceeded 64 KiB")
        data = json.loads(raw)
        text = data.get("message", {}).get("content")
        if data.get("error") or data.get("done") is not True:
            raise ValueError("Ollama response did not complete")
        if not isinstance(text, str) or not text.strip() or len(text) > 8192:
            raise ValueError("Ollama returned empty or oversized NPC text")
        return text.replace("\r", " ").replace("\n", " ").replace("\t", " ")


class Scenario(Composer):
    """One per client. Quest inventory and flags live in the engine player."""

    def __init__(self, client):
        super().__init__(load_world())
        self.client = client
        self.npc_drafts = {}
        self.npc_methods = {}
        self.store = getattr(client, "custom_conversation_store", None)
        self.results = queue.Queue()
        self.worker = None
        self.request = None
        self.endpoint = os.environ.get("TUXEMON_OLLAMA_URL", "")
        self.model = os.environ.get("TUXEMON_OLLAMA_MODEL", "")
        self.provider = "ollama"
        self.message = (
            "Authored scenario. Configure Ollama to receive live NPC replies."
        )

        if self.store is not None:
            memories = self.store.load()
            for index, npc in enumerate(self.world["npcs"]):
                memory = memories[npc["id"]]
                self.npc_drafts[index] = memory.draft
                self.npc_methods[index] = memory.method
                if memory.history:
                    self.conversations[index] = list(memory.history)
            self.draft = self.npc_drafts[self.npc]
            self.method = self.npc_methods[self.npc]

    def persist(self):
        self.npc_drafts[self.npc] = self.draft
        self.npc_methods[self.npc] = self.method
        if self.store is not None:
            self.store.save(
                {
                    npc["id"]: NPCMemory(
                        self.npc_drafts.get(index, ""),
                        self.npc_methods.get(index, 1),
                        tuple(self.conversations.get(index, [])),
                    )
                    for index, npc in enumerate(self.world["npcs"])
                }
            )

    def set_draft(self, text):
        accepted = super().set_draft(text)
        if accepted:
            self.persist()
        return accepted

    def change_method(self, method):
        super().change_method(method)
        self.persist()

    def accept_result(self, token, text=None, error=None):
        accepted = super().accept_result(token, text=text, error=error)
        if accepted:
            self.persist()
        return accepted

    def close_persistence(self):
        self.cancel()
        if self.store is not None:
            self.store.close()

    def select_npc(self, index):
        self.persist()
        self.change_scene(index)
        super().set_draft(self.npc_drafts.get(index, ""))
        self.method = self.npc_methods.get(index, 1)
        self.quit = False
        self.keyboard = False
        self.message = self.scene["opening"]
        self.sync()

    def sync(self):
        player = local_session.player
        self.flags = int(player.game_variables.get("custom_ascent_flags") or 0)
        self.inventory = sum(
            bit
            for name, bit in self.world["items"].items()
            if player.bag.find_item("custom_" + name)
        )

    def confirm_meaning(self):
        self.sync()
        if self.meaning == len(self.scene["replies"]):
            self.message = "No action selected. Draft retained."
        else:
            action = self.scene["replies"][self.meaning]
            if not self.eligible(action):
                self.message = (
                    "Quest guard refused this action. Draft retained."
                )
            else:
                engine = self.client.event_engine
                for name, bit in self.world["items"].items():
                    if action["spend_item"] & bit:
                        engine.execute_action(
                            "add_item", ["custom_" + name, -1]
                        )
                    if action["give_item"] & bit:
                        engine.execute_action(
                            "add_item", ["custom_" + name, 1]
                        )
                engine.execute_action(
                    "set_variable",
                    [
                        f"custom_ascent_flags:{self.flags | action['set_flags']}"
                    ],
                )
                self.context_revision += 1
                self.message = action["text"]
                self.sync()
        self.phase, self.cursor = "reply", 0

    def handle(self, action):
        if self.phase == "reset" and action == "a" and self.cursor == 1:
            self.reset_story()
            return
        self.sync()
        super().handle(action)
        if self.phase == "menu":
            self.keyboard = False

    def reset_quest_state(self):
        self.client.event_engine.execute_action(
            "set_variable", ["custom_ascent_flags:0"]
        )
        for name, bit in self.world["items"].items():
            slug = "custom_" + name
            item = local_session.player.bag.find_item(slug)
            if item:
                self.client.event_engine.execute_action(
                    "add_item", [slug, -item.quantity]
                )
            if self.world["initial_state"]["inventory"] & bit:
                self.client.event_engine.execute_action("add_item", [slug, 1])
        self.sync()

    def reset_story(self):
        self.cancel()
        self.reset_quest_state()
        self.npc_drafts.clear()
        self.npc_methods.clear()
        self.method = 1
        self.conversations.clear()
        self.transcript.clear()
        super().set_draft("")
        self.context_revision += 1
        self.reset_editor()
        self.phase, self.cursor = "editor", 0
        self.message = "Scenario reset. All NPC history and drafts cleared."
        self.persist()
        if self.store is not None and not self.store.writable:
            self.message = "Session reset. Saved file retained because saving is disabled."


def launch(client):
    from tuxemon.entity.npc import NPC

    NPC.create_player(local_session, slug="npc_red")
    client.push_state("BackgroundState")
    client.push_state(
        "WorldState", session=local_session, map_name="custom_last_ascent.tmx"
    )
    client.event_engine.execute_action(
        "teleport", ["player", "custom_last_ascent.tmx", 4, 7]
    )
    from tuxemon.constants.paths import USER_GAME_SAVE_DIR

    client.custom_conversation_store = ConversationStore(
        USER_GAME_SAVE_DIR / "custom-last-ascent",
        os.environ.get("TUXEMON_CUSTOM_PROFILE", "default"),
        tuple(npc["id"] for npc in load_world()["npcs"]),
    )
    client.custom_scenario = Scenario(client)
    client.custom_scenario.reset_quest_state()
