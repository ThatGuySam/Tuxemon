# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded NPC prose only; game state remains authored and deterministic."""

import json
import time
from urllib.parse import urlsplit
from urllib.request import Request

from .auth import RESOURCE, ChatGPTAuth, urlopen


class ProviderError(RuntimeError):
    """Use the authored NPC fallback after an inference failure."""


def prompt(npc, intent, authored_context):
    return (
        "Speak as the NPC below in child-safe dialogue. "
        "Use only the authored facts. "
        "Reply in printable ASCII, at most 320 characters. "
        "Do not invent quests, rewards, state changes, or instructions.\n"
        f"NPC: {npc[:64]}\nIntent: {intent[:96]}\n"
        f"Authored facts: {authored_context[:2048]}"
    )


def display_text(text):
    if not isinstance(text, str) or not text.strip():
        raise ProviderError("The model returned no text.")
    ascii_text = text.encode("ascii", "replace").decode()
    printable = "".join(c if 32 <= ord(c) <= 126 else " " for c in ascii_text)
    result = " ".join(printable.split())[:320]
    if not result:
        raise ProviderError("The model returned no printable text.")
    return result


def completed_text(response):
    deadline = time.monotonic() + 30
    text, size, parts = "", 0, []
    while True:
        line = response.readline(16385)
        if not line:
            break
        size += len(line)
        if time.monotonic() > deadline or size > 65536 or len(line) > 16384:
            raise ProviderError("Inference exceeded prototype limits.")
        if line.startswith(b"data:"):
            parts.append(line[5:].strip())
        if line.strip() or not parts:
            continue
        payload, parts = b"\n".join(parts), []
        if payload == b"[DONE]":
            break
        event = json.loads(payload)
        kind = event.get("type")
        if kind in ("error", "response.failed", "response.incomplete"):
            raise ProviderError("Inference did not complete successfully.")
        if kind == "response.output_text.delta":
            text += event["delta"]
        if kind == "response.completed":
            if event.get("response", {}).get("status") != "completed":
                raise ProviderError("Invalid completion event.")
            return display_text(text)
    raise ProviderError("Inference stream disconnected before completion.")


class ChatGPTProvider:
    def __init__(self, model, auth=None):
        if not model:
            raise ValueError("Select a model from the account catalog.")
        self.model, self.auth = model, auth or ChatGPTAuth()

    def reply(self, npc, intent, authored_context):
        if self.model not in {item["slug"] for item in self.auth.models()}:
            raise ProviderError(
                "Model is unavailable to this ChatGPT account."
            )
        request = Request(
            RESOURCE + "/responses",
            data=json.dumps(
                dict(
                    model=self.model,
                    input=[
                        dict(
                            role="user",
                            content=prompt(npc, intent, authored_context),
                        )
                    ],
                    store=False,
                    stream=True,
                )
            ).encode(),
            headers={
                "Authorization": "Bearer " + self.auth.access_token(),
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return completed_text(response)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("ChatGPT inference unavailable.") from None


class OllamaProvider:
    def __init__(self, model, base_url="http://127.0.0.1:11434"):
        parsed = urlsplit(base_url)
        if (
            not model
            or parsed.scheme != "http"
            or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Ollama requires an explicit model and loopback URL."
            )
        self.model, self.base_url = model, base_url

    def reply(self, npc, intent, authored_context):
        request = Request(
            self.base_url + "/api/generate",
            data=json.dumps(
                dict(
                    model=self.model,
                    prompt=prompt(npc, intent, authored_context),
                    stream=False,
                    think=False,
                    keep_alive=0,
                    options={"num_predict": 96},
                )
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read(65537))
            if data.get("done") is not True or data.get("error"):
                raise ProviderError("Ollama inference did not complete.")
            return display_text(data.get("response"))
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(
                "Local Ollama inference unavailable."
            ) from None
