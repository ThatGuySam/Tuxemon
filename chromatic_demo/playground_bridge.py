"""Owned PyBoy companion. No vendor USB stream or physical RAM access."""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import queue
import secrets
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

BASE, SIZE = 0xC800, 1024
IDLE, REQUESTED, RUNNING, READY, ERROR, CANCELLED = range(6)
CLASSIFY, COMPOSE, EXTERNAL = 1, 2, 3
AUTHORED, PICKER, GENERATOR, PAIRED = 0, 1, 2, 3
TEXT_OFFSET, TEXT_LIMIT = 24, 96
REPLY_OFFSET, REPLY_LIMIT = 128, 192


def ascii_bytes(text: str, limit: int) -> bytes:
    if not isinstance(text, str) or any(
        ord(c) < 32 or ord(c) > 126 for c in text
    ):
        raise ValueError("Text requires printable ASCII")
    data = text.encode("ascii")
    if len(data) > limit:
        raise ValueError(f"Text exceeds {limit} bytes; edit before sending")
    return data


@dataclass(frozen=True)
class Turn:
    sequence: int
    context_revision: int
    draft_revision: int
    scenario: int
    method: int
    operation: int
    text: str
    session_nonce: int = 0


@dataclass(frozen=True)
class Result:
    turn: Turn
    text: str
    intent: int = 255
    source: int = AUTHORED
    error: bool = False
    scores: tuple[tuple[str, float], ...] = ()
    model_id: str | None = None
    model_revision: str | None = None


class Broker:
    """Classify against authored labels; inference never mutates game state."""

    def __init__(
        self,
        content: dict,
        picker=None,
        provider="authored",
        model=None,
        ollama_url="http://127.0.0.1:11434",
    ):
        self.scenarios = content["npcs"]
        self.ollama_url = ollama_url
        if provider == "ollama":
            from .providers import OllamaProvider

            OllamaProvider(model, ollama_url)
        self.picker, self.provider, self.model = picker, provider, model
        if provider in ("ollama", "chatgpt") and not model:
            raise ValueError("Select an explicit model for this provider")

    def run(self, turn: Turn) -> Result:
        if not 0 <= turn.scenario < len(self.scenarios):
            raise ValueError("Unknown scenario")
        scene = self.scenarios[turn.scenario]
        if turn.operation == CLASSIFY:
            options = scene["replies"]
            if self.picker is None:
                # No heuristic may masquerade as a live classifier.
                raise RuntimeError(
                    "Live classifier unavailable; ROM owns authored fallback"
                )
            labels = {
                option["label"]: option.get(
                    "classifier_label",
                    option.get("label_description", option["label"]),
                )
                for option in options
            }
            picked = self.picker.classify(
                turn.text, labels, context=scene.get("opening", "")
            )
            receipt = {
                "scores": tuple(picked.scores.items()),
                "model_id": picked.model_id,
                "model_revision": picked.model_revision,
            }
            index = next(
                (
                    index
                    for index, option in enumerate(options)
                    if option["label"] == picked.label
                ),
                None,
            )
            if index is None or not 0 <= index < len(options):
                return Result(
                    turn,
                    "Meaning unclear. Please choose a topic or edit your message.",
                    source=PICKER,
                    **receipt,
                )
            return Result(
                turn, options[index]["text"], index, PICKER, **receipt
            )
        if turn.operation == COMPOSE:
            if self.provider not in ("ollama", "chatgpt"):
                return Result(turn, turn.text)
            method_instruction = {
                0: "The draft contains a selected intent, topic and stance.",
                1: "The draft contains selected keywords; infer grammar conservatively.",
                2: "The draft may contain word initials mixed with spelled keywords. Expand only when meaning is clear.",
            }.get(turn.method, "The draft contains player-entered text.")
            actions = "; ".join(
                option.get(
                    "classifier_label",
                    option.get("label_description", option["label"]),
                )
                for option in scene["replies"]
            )
            prompt = (
                "You compose the PLAYER'S outgoing utterance to the NPC, never the NPC's reply. "
                "Preserve names, negation, quantities, uncertainty and speaker stance. Do not add facts, "
                "commitments or world actions. Background actions are context, not a closed list: unusual "
                "questions are allowed. If the intended meaning is ambiguous, return the literal draft unchanged. "
                "Printable ASCII only, at most 96 characters. Output only the player utterance.\n"
                f"NPC: {scene.get('name', 'NPC')}\nBackground: {scene.get('opening', '')}\n"
                f"Relevant actions: {actions}\nInput method: {method_instruction}\nDraft: {turn.text}"
            )
            if self.provider == "chatgpt":
                from .providers import ChatGPTProvider

                text = ChatGPTProvider(self.model).generate(prompt, raw=True)
                ascii_bytes(text, TEXT_LIMIT)
                if not text.strip():
                    raise ValueError("Empty model response")
                return Result(
                    turn, text, source=GENERATOR, model_id=self.model
                )
            request = Request(
                self.ollama_url + "/api/generate",
                data=json.dumps(
                    {
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "think": False,
                        "keep_alive": 0,
                        "options": {"num_predict": 64},
                    }
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read(65537))
            if data.get("done") is not True:
                raise ValueError("Incomplete model response")
            text = data["response"]
            ascii_bytes(text, TEXT_LIMIT)
            if not text:
                raise ValueError("Empty model response")
            return Result(turn, text, source=GENERATOR, model_id=self.model)
        raise ValueError("Unsupported inference operation")


class Controller:
    """The sole owner of emulator memory; call tick only on its creator thread."""

    def __init__(self, emulator, broker, executor=None):
        self.emulator, self.broker = emulator, broker
        self.owner = threading.get_ident()
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.owns_executor = executor is None
        self.pending = None
        self.frame = 0
        self.last_result = None
        self.nonce = secrets.randbits(32) or 1
        self.handshake_written = False
        self.external = queue.Queue(maxsize=1)
        self.completed = queue.SimpleQueue()

    def _read(self, offset, length=1):
        if not length:
            return b""
        return bytes(
            self.emulator.memory[BASE + offset : BASE + offset + length]
        )

    def _write(self, offset, data):
        self.emulator.memory[BASE + offset : BASE + offset + len(data)] = list(
            data
        )

    def queue_external(self, text: str):
        """HTTP thread queues text; it never accesses PyBoy or commits a message."""
        ascii_bytes(text, TEXT_LIMIT)
        if not text.strip():
            raise ValueError("Empty external text")
        self.external.put_nowait(text)

    def _turn(self):
        h = self._read(6, 7)
        operation, sequence, context, draft, scenario, method, length = h
        if length > TEXT_LIMIT:
            raise ValueError("Invalid request length")
        text = self._read(TEXT_OFFSET, length).decode("ascii")
        ascii_bytes(text, TEXT_LIMIT)
        return Turn(
            sequence,
            context,
            draft,
            scenario,
            method,
            operation,
            text,
            self.nonce,
        )

    def _result(self, result):
        if self._read(5)[0] != RUNNING or self._turn() != result.turn:
            return False
        data = ascii_bytes(result.text, REPLY_LIMIT)
        self._write(REPLY_OFFSET, data + bytes(REPLY_LIMIT - len(data)))
        self._write(13, bytes((len(data), result.intent, result.source)))
        self._write(5, bytes((ERROR if result.error else READY,)))
        self.last_result = result
        return True

    def _worker(self, turn):
        try:
            result = self.broker.run(turn)
            ascii_bytes(result.text, REPLY_LIMIT)
        except Exception:  # noqa: BLE001 - Model adapters fail closed to the ROM fallback.
            result = Result(
                turn,
                "Model unavailable. Your draft is preserved; choose an authored topic.",
                error=True,
            )
        self.completed.put(result)

    def tick(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError(
                "Emulator memory accessed outside its owner thread"
            )
        self.frame = (self.frame + 1) & 0xFFFFFFFF
        if self._read(0, 5) != b"TXMB\x01":
            return
        if (
            self.handshake_written
            and int.from_bytes(self._read(20, 4), "little") != self.nonce
        ):
            self.nonce = secrets.randbits(32) or 1
            self.pending = None
        self.handshake_written = True
        self._write(16, self.frame.to_bytes(4, "little"))
        self._write(20, self.nonce.to_bytes(4, "little"))
        while not self.completed.empty():
            result = self.completed.get()
            try:
                self._result(result)
            except (ValueError, UnicodeError):
                pass
            if self.pending == result.turn:
                self.pending = None
        status = self._read(5)[0]
        if status not in (REQUESTED, RUNNING):
            return
        try:
            turn = self._turn()
            if turn.operation == EXTERNAL:
                if turn.method != 8:
                    raise ValueError(
                        "External input requires paired entry mode"
                    )
                self._write(5, bytes((RUNNING,)))
                try:
                    text = self.external.get_nowait()
                except queue.Empty:
                    return
                self._result(Result(turn, text, source=PAIRED))
            elif status == REQUESTED and self.pending is None:
                self._write(5, bytes((RUNNING,)))
                self.pending = turn
                self.executor.submit(self._worker, turn)
        except (ValueError, UnicodeError, IndexError):
            self._write(5, bytes((ERROR,)))

    def close(self):
        if self.owns_executor:
            self.executor.shutdown(wait=False, cancel_futures=True)


ENTRY_PAGE = b"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tuxemon paired entry</title><main><h1>Send text to your game draft</h1>
<p>Choose Paired entry, then Receive in the Mac game. Text waits for your review there.
This companion does not send text to the physical Chromatic.</p>
<form id="entry"><p><label for="key">Pairing key</label><br>
<input id="key" type="password" required autocomplete="off"></p>
<p><label for="text">Your message (up to 96 printable ASCII characters)</label><br>
<textarea id="text" maxlength="96" rows="4" cols="36" required></textarea></p>
<button id="send" type="submit">Queue draft</button></form>
<p id="status" role="status" aria-live="polite"></p></main>
<script>
const form = document.querySelector('#entry');
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = document.querySelector('#status');
  const button = document.querySelector('#send');
  const text = document.querySelector('#text').value;
  if (!/^[ -~]{1,96}$/.test(text) || !text.trim()) {
    status.textContent = 'Enter 1 to 96 printable ASCII characters.';
    return;
  }
  button.disabled = true;
  status.textContent = 'Queuing your draft...';
  try {
    const response = await fetch('/v1/input', {
      method: 'POST',
      headers: {'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + document.querySelector('#key').value},
      body: JSON.stringify({text})
    });
    const result = await response.json();
    status.textContent = response.ok
      ? 'Queued. Choose Receive in paired entry, then review and send in the game.'
      : 'Could not queue: ' + result.error;
  } catch (error) {
    status.textContent = 'Connection unavailable. Your text remains here.';
  } finally { button.disabled = false; }
});
</script></html>"""


class PairedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(5)
        try:
            if isinstance(request, ssl.SSLSocket):
                request.do_handshake()
        except OSError:
            request.close()
            raise
        return request, address

    def handle_error(self, request, client_address):
        pass


def unique_object(pairs):
    if len(dict(pairs)) != len(pairs):
        raise ValueError("Duplicate JSON fields")
    return dict(pairs)


def paired_server(
    controller, secret, bind="127.0.0.1", port=0, cert=None, key=None
):
    try:
        local = ipaddress.ip_address(bind).is_loopback
    except ValueError:
        local = bind == "localhost"
    if bool(cert) != bool(key) or (not local and not cert):
        raise ValueError("LAN entry requires TLS certificate and key")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(5)
            super().setup()

        def log_message(self, *args):
            pass

        def respond(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def do_GET(self):
            if self.path != "/":
                self.respond(404, {"error": "unknown_path"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(ENTRY_PAGE)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(ENTRY_PAGE)

        def do_POST(self):
            self.connection.settimeout(5)
            auth = self.headers.get_all("Authorization", [])
            if len(auth) != 1 or not hmac.compare_digest(
                auth[0].encode(), ("Bearer " + secret).encode()
            ):
                self.respond(401, {"error": "unauthorized"})
                return
            if self.path != "/v1/input":
                self.respond(404, {"error": "unknown_path"})
                return
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                    raise ValueError("Invalid framing")
                if (
                    len(lengths[0]) > 6
                    or not lengths[0].isascii()
                    or not lengths[0].isdigit()
                ):
                    raise ValueError("Invalid Content-Length")
                size = int(lengths[0])
                if not 0 < size <= 1024:
                    raise ValueError("Invalid body length")
                body = self.rfile.read(size)
                if len(body) != size:
                    raise ValueError("Incomplete request")
                value = json.loads(body, object_pairs_hook=unique_object)
                if not isinstance(value, dict) or set(value) != {"text"}:
                    raise ValueError("Expected text only")
                controller.queue_external(value["text"])
            except queue.Full:
                self.respond(409, {"error": "previous_text_pending"})
                return
            except (ValueError, TypeError, OSError):
                self.respond(400, {"error": "invalid_text"})
                return
            self.respond(202, {"queued": True, "committed": False})

    server = PairedHTTPServer((bind, port), Handler)
    if cert:
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(
                server.socket, server_side=True, do_handshake_on_connect=False
            )
        except Exception:
            server.server_close()
            raise
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--picker-model")
    parser.add_argument(
        "--provider", choices=("authored", "ollama"), default="authored"
    )
    parser.add_argument("--model")
    parser.add_argument("--window", choices=("SDL2", "null"), default="SDL2")
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--pairing-file", type=Path)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    args = parser.parse_args(argv)
    from pyboy import PyBoy

    content = json.loads(args.content.read_text())
    picker = None
    if args.picker_model:
        try:
            from .npc_picker import GLiClassPicker

            picker = GLiClassPicker.from_local_model(args.picker_model)
        except Exception as error:  # noqa: BLE001 - Optional model startup reports a safe error class.
            print(
                json.dumps(
                    {
                        "picker": "unavailable",
                        "fallback": "authored",
                        "error_class": type(error).__name__,
                    }
                ),
                flush=True,
            )
    broker = Broker(content, picker, args.provider, args.model)
    emulator = PyBoy(
        str(args.rom.resolve(strict=True)),
        window=args.window,
        scale=4,
        sound_volume=0,
    )
    controller = Controller(emulator, broker)
    server = None
    try:
        if args.pairing_file:
            from .server import pairing_secret

            secret = pairing_secret(
                args.pairing_file, Path(__file__).resolve().parents[1]
            )
            server = paired_server(
                controller,
                secret,
                args.bind,
                args.port,
                args.tls_cert,
                args.tls_key,
            )
            threading.Thread(target=server.serve_forever, daemon=True).start()
            scheme = "https" if args.tls_cert else "http"
            print(
                json.dumps(
                    {
                        "input_endpoint": f"{scheme}://{args.bind}:{server.server_port}/v1/input",
                        "transport": "owned_pyboy",
                        "physical_live_models": False,
                    }
                ),
                flush=True,
            )
        count = 0
        while emulator.tick():
            controller.tick()
            count += 1
            if args.frames and count >= args.frames:
                break
    finally:
        if server:
            server.shutdown()
            server.server_close()
        controller.close()
        emulator.stop(save=False)


if __name__ == "__main__":
    main()
