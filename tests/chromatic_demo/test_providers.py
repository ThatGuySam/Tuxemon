# SPDX-License-Identifier: GPL-3.0-or-later
"""Responses are SYNTHETIC protocol fixtures, not measured inference."""

import io
import json
from unittest.mock import Mock, patch

import pytest

from chromatic_demo.providers import (
    ChatGPTProvider,
    OllamaProvider,
    ProviderError,
    completed_text,
    display_text,
)


def synthetic_stream(*events):
    return io.BytesIO(
        b"".join(
            b"data: " + json.dumps(event).encode() + b"\n\n"
            for event in events
        )
    )


def test_stream_requires_completed_after_text():
    delta = dict(type="response.output_text.delta", delta="SYNTHETIC dialogue")
    complete = dict(
        type="response.completed", response={"status": "completed"}
    )
    assert completed_text(synthetic_stream(delta, complete)) == delta["delta"]
    for terminal in (
        None,
        dict(type="response.failed"),
        dict(type="response.incomplete"),
        dict(type="error"),
        dict(type="response.completed", response={"status": "failed"}),
    ):
        events = [delta] + ([terminal] if terminal else [])
        with pytest.raises(ProviderError):
            completed_text(synthetic_stream(*events))


def test_sse_multiline_size_limits_and_ascii():
    response = io.BytesIO(
        b'data: {"type":"response.output_text.delta",\n'
        b'data: "delta":"SYNTHETIC"}\n\n'
        b'data: {"type":"response.completed",\n'
        b'data: "response":{"status":"completed"}}\n\n'
    )
    assert completed_text(response) == "SYNTHETIC"
    with pytest.raises(ProviderError, match="limits"):
        completed_text(io.BytesIO(b"data: " + b"x" * 17000 + b"\n"))
    result = display_text("SYNTHETIC \u00e9\x00\x07\n" + "x" * 1000)
    assert len(result) == 320
    assert all(32 <= ord(char) <= 126 for char in result)


@pytest.mark.parametrize(
    "control",
    [
        pytest.param("\x00", id="null"),
        pytest.param("\x1b", id="escape"),
        pytest.param("\x7f", id="delete"),
    ],
)
def test_synthetic_control_bytes_become_word_boundaries(control):
    result = display_text("SYNTHETIC" + control + "dialogue")
    assert result == "SYNTHETIC dialogue"
    assert all(32 <= ord(char) <= 126 for char in result)


def test_synthetic_only_controls_are_rejected():
    with pytest.raises(ProviderError, match="no printable text"):
        display_text("\x00\x1b\x7f")
    events = synthetic_stream(
        dict(type="response.output_text.delta", delta="\x00\x1b"),
        dict(type="response.completed", response={"status": "completed"}),
    )
    with pytest.raises(ProviderError, match="no printable text"):
        completed_text(events)


def test_synthetic_multiline_dialogue_keeps_word_order():
    assert display_text("  SYNTHETIC\n\tdialogue\r\nwrapped  ") == (
        "SYNTHETIC dialogue wrapped"
    )


def test_chatgpt_public_endpoint_and_payload():
    auth = Mock()
    auth.models.return_value = [{"slug": "SYNTHETIC_MODEL"}]
    auth.access_token.return_value = "SYNTHETIC_ACCESS_NOT_REAL"
    provider = ChatGPTProvider("SYNTHETIC_MODEL", auth)
    stream = synthetic_stream(
        dict(type="response.output_text.delta", delta="SYNTHETIC reply"),
        dict(type="response.completed", response={"status": "completed"}),
    )
    with patch("chromatic_demo.providers.urlopen", return_value=stream) as req:
        assert (
            provider.reply("NPC", "greet", "Authored facts")
            == "SYNTHETIC reply"
        )
        request = req.call_args.args[0]
        assert request.full_url == "https://api.openai.com/v1/responses"
        payload = json.loads(request.data)
        assert payload["store"] is False and payload["stream"] is True
        assert set(payload) == {"model", "input", "store", "stream"}
    auth.models.return_value = []
    with pytest.raises(ProviderError, match="unavailable"):
        provider.reply("NPC", "greet", "Authored facts")


def test_ollama_explicit_loopback_model_and_done_gate():
    for url in (
        "https://localhost:11434",
        "http://example.com",
        "http://localhost:11434/path",
        "http://user@localhost:11434",
    ):
        with pytest.raises(ValueError):
            OllamaProvider("SYNTHETIC_MODEL", url)
    with pytest.raises(ValueError):
        OllamaProvider("")
    provider = OllamaProvider("SYNTHETIC_MODEL")
    for done in (False, True):
        response = io.BytesIO(
            json.dumps(dict(done=done, response="SYNTHETIC reply")).encode()
        )
        with patch(
            "chromatic_demo.providers.urlopen", return_value=response
        ) as req:
            if done:
                assert (
                    provider.reply("NPC", "greet", "facts")
                    == "SYNTHETIC reply"
                )
            else:
                with pytest.raises(ProviderError, match="complete"):
                    provider.reply("NPC", "greet", "facts")
            payload = json.loads(req.call_args.args[0].data)
            assert payload["keep_alive"] == 0
            assert payload["think"] is False
