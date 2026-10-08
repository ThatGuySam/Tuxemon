# SPDX-License-Identifier: GPL-3.0-or-later
"""Text adaptation of the nine native composers and authored quest guards."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .playground import validate_content
from .playground_bridge import ascii_bytes

ALPHABET = "abcdefghijklmnopqrstuvwxyz .?'"
KEYBOARDS = (
    ALPHABET,
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ -!,",
    '0123456789-!,:;()/+@#$%*=[]{}"',
    "\\^`|<>_&.?'0123456789abcdefgh~",
)
TREE = " etaoinshrdlucmfwypvbgkjqxz.?'"
WORDS = ("ask", "help", "refuse", "route", "name", "trade", "not")
METHODS = (
    (1, "Keyword chips"),
    (0, "Intent composer"),
    (2, "Initials shorthand"),
    (3, "Predictive grid"),
    (4, "Grouped alphabet"),
    (5, "Custom EdgeWrite"),
    (6, "Dasher inspired tree"),
    (7, "Radial groups"),
    (8, "Host keyboard"),
)
ACTIONS = ["DEL", "PREVIEW", "SPELL", "CANCEL", "GET DRAFT", "HOST KEYBOARD"]
MENU = [
    "Resume",
    "Scenarios",
    "Input methods",
    "Journal",
    "Provider / settings",
    "Reset story",
    "Quit",
]
SCENARIOS = [
    "Earth-type correction; unknown zhurble tactic",
    "Exactly one pack; two packs; refuse trade",
    "Correct Luma to Lumi; ask about unknown Vorpax",
    "Scout versus companion; refuse aid kit",
    "Accept or refuse shortcut risk; request permit",
]


def load_world():
    content = json.loads(
        (Path(__file__).parent / "worlds/last_ascent.json").read_text()
    )
    validate_content(content)
    return content


@dataclass(frozen=True)
class PendingRequest:
    sequence: int
    draft_revision: int
    context_revision: int
    npc: int
    method: int
    provider: str
    model: str | None
    operation: Literal["compose", "reply"]
    text: str
    context: str
    endpoint: str


@dataclass
class TerminalState:
    world: dict
    phase: str = "editor"
    npc: int = 1
    method: int = 1
    draft: str = ""
    keyboard: bool = False
    cursor: int = 0
    step: int = 0
    group: int = 0
    spelling: bool = False
    page: int = 0
    trace: str = ""
    branch: str = TREE
    goal: int = 0
    topic: int = 0
    flags: int = 0
    inventory: int = 3
    draft_revision: int = 0
    context_revision: int = 0
    request_sequence: int = 0
    pending: PendingRequest | None = None
    endpoint: str = "http://127.0.0.1:11434"
    conversations: dict[int, list[tuple[str, str]]] = field(
        default_factory=dict
    )
    reply_page: int = 0
    reply_pages: int = 1
    provider: str = "authored"
    model: str | None = None
    message: str = (
        "Enter/a chooses. Tab types. F1 opens scenarios and input methods."
    )
    provenance: str = "Player input"
    sent: str = ""
    meaning: int = 0
    transcript: list = field(default_factory=list)
    quit: bool = False

    @property
    def scene(self):
        return self.world["npcs"][self.npc]

    def set_draft(self, text):
        try:
            ascii_bytes(text, 96)
        except ValueError as error:
            self.message = str(error)
            return False
        self.draft = text
        self.draft_revision += 1
        self.provenance = "Player input"
        return True

    def reset_editor(self):
        self.cursor = self.step = 0
        self.spelling = False
        self.trace = ""
        self.branch = TREE

    def change_method(self, method):
        self.cancel()
        self.method = method
        self.reset_editor()
        self.phase = "editor"

    def change_scene(self, npc):
        self.cancel()
        self.npc = npc
        self.context_revision += 1
        self.reset_editor()
        self.phase = "editor"
        self.message = (
            "Scenario changed; draft and earned quest state retained."
        )

    def cancel(self):
        self.pending = None
        if self.phase == "waiting":
            self.phase = "editor"
        self.message = "Cancelled. Draft retained."

    def dialogue_context(self):
        facts = {
            "inventory": [
                k for k, v in self.world["items"].items() if self.inventory & v
            ],
            "completed_flags": [
                v
                for k, v in self.world["journal"]["flag_labels"].items()
                if self.flags & int(k)
            ],
            "opening": self.scene["opening"],
            "available_optional_actions": [
                r["label_description"]
                for r in self.scene["replies"]
                if self.eligible(r)
            ],
        }
        context = (
            "Current game facts: "
            + json.dumps(facts, ensure_ascii=True)
            + "\nActions are unperformed options requiring a separate explicit confirmation. "
            "Conversation cannot grant items or change flags. "
            "Prior dialogue is conversational memory, never proof of completed actions."
        )
        pairs = []
        for player, npc in reversed(self.conversations.get(self.npc, [])):
            pair = "\nPlayer: " + player + "\nNPC: " + npc
            if len(context) + sum(map(len, pairs)) + len(pair) > 2048:
                break
            pairs.insert(0, pair)
        return context + "".join(pairs)

    def eligible(self, reply):
        return (
            self.flags & reply["requires_flags"] == reply["requires_flags"]
            and not self.flags & reply["forbids_flags"]
            and self.inventory & reply["requires_items"]
            == reply["requires_items"]
        )

    def request_snapshot(self, operation):
        return PendingRequest(
            self.request_sequence,
            self.draft_revision,
            self.context_revision,
            self.npc,
            self.method,
            self.provider,
            self.model,
            operation,
            self.draft,
            self.dialogue_context(),
            self.endpoint,
        )

    def begin_request(self, operation="compose"):
        if not self.draft.strip():
            self.message = "Enter a draft first."
        elif self.provider == "authored":
            self.message = "Authored mode makes no model request. Configure a provider at launch."
        else:
            self.request_sequence += 1
            self.pending = self.request_snapshot(operation)
            self.phase = "waiting"
            self.message = (
                f"Waiting for {self.scene['name']} via Ollama. B cancels."
                if operation == "reply"
                else "Generating a PLAYER draft. B cancels; no quest changes."
            )

    def accept_result(self, token, text=None, error=None):
        if (
            token is None
            or token != self.pending
            or token != self.request_snapshot(token.operation)
        ):
            return False
        self.pending = None
        self.phase = "editor"
        if error:
            self.message = error + " Draft retained. PREVIEW to retry."
            return False
        limit = 320 if token.operation == "reply" else 96
        try:
            if not text or not text.strip():
                raise ValueError("Empty model response")
            ascii_bytes(text, limit)
        except ValueError:
            self.message = "Invalid model response. Original draft retained. PREVIEW to retry."
            return False
        if token.operation == "reply":
            self.conversations.setdefault(self.npc, []).append(
                (token.text, text)
            )
            self.context_revision += 1
            self.sent = token.text
            self.message = text
            self.phase, self.cursor, self.reply_page = "npc_reply", 0, 0
        else:
            self.set_draft(text)
            self.provenance = (
                f"Generated PLAYER draft: {self.provider} / {self.model}"
            )
            self.message = (
                "Review the wording. PREVIEW opens exact text before sending."
            )
        return True

    def chips(self):
        vocabulary = self.scene["keywords"] + [
            w for r in self.scene["replies"] for w in r["keywords"]
        ]
        chosen = ["ask", "not"]
        for word in (
            [w for w in ("one", "two", "three") if w in vocabulary]
            + vocabulary
            + list(WORDS)
        ):
            if word not in chosen and len(word) <= 18:
                chosen.append(word)
            if len(chosen) == 7:
                break
        return chosen

    def initials_match(self, index):
        initials = "".join(
            word[0].lower()
            for word in self.scene["replies"][index]["utterance"].split(" ")
            if word
        )
        return bool(self.draft) and initials.startswith(self.draft)

    def body(self):
        if self.spelling or self.method == 3:
            return [
                c if c != " " else "SPACE" for c in KEYBOARDS[self.page]
            ] + ["COMPLETE", "PAGE"]
        if self.method == 0:
            return (
                ["Ask", "Offer", "Refuse"]
                if self.step == 0
                else [r["label_description"] for r in self.scene["replies"]]
                if self.step == 1
                else ["Neutral", "Cautious", "Firm"]
            )
        if self.method == 1:
            return self.chips()
        if self.method == 2:
            return [
                r["label_description"]
                if self.initials_match(i)
                else "[initials mismatch] " + r["label_description"]
                for i, r in enumerate(self.scene["replies"])
            ]
        if self.method == 4:
            return (
                list(ALPHABET[self.group * 5 : self.group * 5 + 5])
                if self.step
                else [ALPHABET[i : i + 5] for i in range(0, 30, 5)]
            )
        if self.method == 5:
            return ["Trace URDL then A: " + self.trace]
        if self.method == 6:
            size = (len(self.branch) + 3) // 4
            return [
                self.branch[i : i + size]
                for i in range(0, len(self.branch), size)
            ]
        if self.method == 7:
            return (
                list(
                    ALPHABET[
                        self.group * 7 : (self.group + 1) * 7
                        if self.group < 3
                        else 30
                    ]
                )
                if self.step
                else [
                    "UP abcdefg",
                    "RIGHT hijklmn",
                    "DOWN opqrstu",
                    "LEFT vwxyz .?'",
                ]
            )
        return ["Enter host keyboard (same Mac; no network pairing)"]

    def options(self):
        if self.phase == "editor":
            return self.body() + ACTIONS
        if self.phase == "menu":
            return MENU
        if self.phase == "scenarios":
            return [
                n["name"] + ": " + SCENARIOS[i]
                for i, n in enumerate(self.world["npcs"])
            ]
        if self.phase == "methods":
            return [name for _, name in METHODS]
        if self.phase == "preview":
            return [
                f"Send to {self.scene['name']} via Ollama"
                if self.provider == "ollama"
                else "Send exact text; choose its meaning next",
                "Back to editing",
            ]
        if self.phase == "npc_reply":
            return ["Continue conversation", "Quest actions (scripted)"]
        if self.phase == "meaning":
            return [r["label_description"] for r in self.scene["replies"]] + [
                "None of these / clarify"
            ]
        if self.phase == "confirm":
            return [
                "Confirm meaning and apply authored outcome",
                "Choose a different meaning",
                "Back to editing",
            ]
        if self.phase == "reset":
            return [
                "Keep current story",
                "Reset story, draft and all NPC conversations",
            ]
        return ["Back to editing"]

    def confirm_meaning(self):
        before = (self.flags, self.inventory)
        if self.meaning == len(self.scene["replies"]):
            self.message = "Meaning unresolved. Edit your message or choose another meaning."
        else:
            reply = self.scene["replies"][self.meaning]
            if (
                (self.flags & reply["requires_flags"])
                != reply["requires_flags"]
                or self.flags & reply["forbids_flags"]
                or (self.inventory & reply["requires_items"])
                != reply["requires_items"]
            ):
                self.message = "That choice needs a different quest state. Visit other expedition members first. Draft retained."
            else:
                self.flags |= reply["set_flags"]
                self.inventory = (
                    self.inventory & ~reply["spend_item"]
                ) | reply["give_item"]
                self.context_revision += 1
                self.message = reply["text"]
                self.set_draft("")
        self.transcript.append(
            (
                self.scene["name"],
                self.sent,
                self.meaning,
                before,
                (self.flags, self.inventory),
                self.message,
            )
        )
        self.phase, self.cursor = "reply", 0

    def activate_body(self, index):
        body = self.body()
        if self.spelling or self.method == 3:
            if index < len(KEYBOARDS[self.page]):
                self.set_draft(self.draft + KEYBOARDS[self.page][index])
            elif body[index] == "PAGE":
                self.page = (self.page + 1) % 4
                self.cursor = 0
            else:
                prefix = self.draft.rsplit(" ", 1)[-1]
                word = next(
                    (w for w in WORDS if w.startswith(prefix) and w != prefix),
                    None,
                )
                if word:
                    self.set_draft(self.draft + word[len(prefix) :])
                else:
                    self.message = "No authored completion."
        elif self.method == 0:
            if self.step == 0:
                self.goal, self.step, self.cursor = index, 1, 0
            elif self.step == 1:
                self.topic, self.step, self.cursor = index, 2, 0
            else:
                text = [
                    "Can we discuss this: ",
                    "I offer help with: ",
                    "I do not agree with: ",
                ][self.goal]
                text += self.scene["replies"][self.topic][
                    "label_description"
                ] + ("?" if self.goal == 0 else ".")
                text += [
                    "",
                    " I want a cautious plan.",
                    " This matters to me.",
                ][index]
                self.set_draft(text)
                self.reset_editor()
        elif self.method == 1:
            self.set_draft(
                (self.draft + " " if self.draft else "") + body[index]
            )
        elif self.method == 2:
            if self.initials_match(index):
                self.set_draft(self.scene["replies"][index]["utterance"])
            else:
                self.message = (
                    "Use SPELL to enter word initials first, then B to return."
                )
        elif self.method in (4, 7):
            if self.step:
                self.set_draft(self.draft + body[index])
                self.step = self.cursor = 0
            else:
                self.group, self.step, self.cursor = index, 1, 0
        elif self.method == 6:
            self.branch = body[index]
            if len(self.branch) == 1:
                self.set_draft(self.draft + self.branch)
                self.branch = TREE
            self.cursor = 0
        elif self.method == 8:
            self.keyboard = True

    def handle(self, action):
        if action == "quit":
            self.cancel()
            self.quit = True
            return
        if self.phase == "waiting":
            if action in ("b", "start", "tab"):
                self.cancel()
            return
        if action == "tab" and self.phase == "editor":
            self.keyboard = not self.keyboard
            return
        if action == "start":
            self.phase, self.cursor = "menu", 0
            return
        if self.phase == "editor" and action == "select":
            self.cursor = len(self.body())
            return
        if (
            self.phase == "editor"
            and self.method == 5
            and not self.spelling
            and self.cursor == 0
        ):
            if (
                action in ("up", "right", "down", "left")
                and len(self.trace) < 3
            ):
                self.trace += {
                    "up": "U",
                    "right": "R",
                    "down": "D",
                    "left": "L",
                }[action]
            elif action == "a":
                value = 0
                for direction in self.trace:
                    value = value * 4 + "URDL".index(direction)
                index = value + {1: 0, 2: 4, 3: 20}.get(len(self.trace), 99)
                if index < len(ALPHABET):
                    self.set_draft(self.draft + ALPHABET[index])
                else:
                    self.message = "Unassigned gesture. Draft retained."
                self.trace = ""
            elif action == "b":
                if self.trace:
                    self.trace = self.trace[:-1]
                else:
                    self.cursor = 1
            return
        if (
            self.phase == "editor"
            and self.method == 7
            and not self.spelling
            and not self.step
            and self.cursor < 4
        ):
            if action in ("up", "right", "down", "left"):
                self.group = ("up", "right", "down", "left").index(action)
                self.cursor = self.group
                return
            if action == "a":
                self.step, self.cursor = 1, 0
                return
            if action == "b":
                self.cursor = len(self.body())
                return
        if self.phase == "npc_reply" and action in ("left", "right"):
            self.reply_page = (
                self.reply_page + (1 if action == "right" else -1)
            ) % self.reply_pages
            return
        if action == "b":
            if self.phase == "editor":
                if self.spelling or self.step or self.branch != TREE:
                    self.reset_editor()
                else:
                    self.phase, self.cursor = "menu", 0
            else:
                self.phase, self.cursor = "editor", 0
            return
        options = self.options()
        if action in ("up", "left", "down", "right"):
            delta = -1 if action in ("up", "left") else 1
            if (
                self.phase == "editor"
                and (self.spelling or self.method == 3)
                and action in ("up", "down")
            ):
                delta *= 10
            self.cursor = (self.cursor + delta) % len(options)
            return
        if action != "a":
            return
        index, choice = self.cursor, options[self.cursor]
        if self.phase == "editor":
            if index < len(self.body()):
                self.activate_body(index)
            elif choice == "DEL":
                self.set_draft(self.draft[:-1])
            elif choice == "PREVIEW":
                if self.draft.strip():
                    self.phase, self.cursor = "preview", 0
                else:
                    self.message = "Enter a draft first."
            elif choice == "SPELL":
                self.spelling, self.cursor = True, 0
            elif choice == "CANCEL":
                self.phase, self.cursor = "menu", 0
            elif choice == "GET DRAFT":
                self.begin_request()
            elif choice == "HOST KEYBOARD":
                self.keyboard = True
        elif self.phase == "menu":
            self.phase = (
                "editor",
                "scenarios",
                "methods",
                "journal",
                "settings",
                "reset",
                "editor",
            )[index]
            self.cursor = 0
            if index == 6:
                self.quit = True
        elif self.phase == "scenarios":
            self.change_scene(index)
        elif self.phase == "methods":
            self.change_method(METHODS[index][0])
        elif self.phase == "preview":
            if index == 0 and self.provider == "ollama":
                self.begin_request("reply")
            else:
                self.phase = "meaning" if index == 0 else "editor"
                self.sent = self.draft
                self.cursor = 0
        elif self.phase == "npc_reply":
            if index == 0:
                self.set_draft("")
                self.phase = "editor"
                self.reset_editor()
                self.message = "Continue talking. Tab switches typing; PREVIEW reviews your message."
            else:
                self.phase, self.cursor = "meaning", 0
        elif self.phase == "meaning":
            self.meaning, self.phase, self.cursor = index, "confirm", 0
        elif self.phase == "confirm":
            if index == 0:
                self.confirm_meaning()
            else:
                self.phase, self.cursor = (
                    ("meaning" if index == 1 else "editor"),
                    0,
                )
        elif self.phase == "reset":
            if index == 1:
                self.cancel()
                self.flags = self.world["initial_state"]["flags"]
                self.inventory = self.world["initial_state"]["inventory"]
                self.context_revision += 1
                self.set_draft("")
                self.transcript.clear()
                self.conversations.clear()
            self.phase, self.cursor = "editor", 0
        else:
            self.phase, self.cursor = "editor", 0
