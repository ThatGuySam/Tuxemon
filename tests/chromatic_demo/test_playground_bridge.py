"""Protocol and real HTTP tests, without model or hardware assumptions."""

import io
import json
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from chromatic_demo.playground_bridge import (
    BASE,
    CLASSIFY,
    COMPOSE,
    ERROR,
    EXTERNAL,
    READY,
    REQUESTED,
    RUNNING,
    Broker,
    Controller,
    Turn,
    paired_server,
)


class MemoryEmulator:
    def __init__(self):
        self.memory = bytearray(65536)
        self.memory[BASE : BASE + 5] = b"TXMB\x01"

    def request(
        self, text="Do not open the gate.", operation=CLASSIFY, method=3
    ):
        data = text.encode("ascii")
        self.memory[BASE + 6 : BASE + 13] = bytes(
            (operation, 7, 2, 3, 0, method, len(data))
        )
        self.memory[BASE + 24 : BASE + 24 + len(data)] = data
        self.memory[BASE + 5] = REQUESTED


class DeferredExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, function, argument):
        self.calls.append((function, argument))

    def finish(self):
        function, argument = self.calls.pop(0)
        function(argument)


class PickerResult:
    label = "Keep closed"
    scores: ClassVar[dict[str, float]] = {"Open": 0.1, "Keep closed": 0.9}
    model_id = "test-only-picker"
    model_revision = "test-only-revision"


class RecordingPicker:
    def classify(self, text, labels, context=""):
        self.call = (text, labels, context)
        return PickerResult()


CONTENT = {
    "npcs": [
        {
            "opening": "A gate is closed.",
            "replies": [
                {"label": "Open", "text": "I will open it."},
                {
                    "label": "Keep closed",
                    "classifier_label": "refuse to open the gate",
                    "text": "It will stay closed.",
                },
            ],
        }
    ]
}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.memory = MemoryEmulator()
        self.executor = DeferredExecutor()
        self.picker = RecordingPicker()
        self.controller = Controller(
            self.memory, Broker(CONTENT, self.picker), self.executor
        )

    def test_classification_does_not_complete_until_worker_returns(self):
        self.memory.request()
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], RUNNING)
        self.executor.finish()
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], READY)
        self.assertEqual(self.memory.memory[BASE + 14], 1)
        self.assertEqual(self.picker.call[0], "Do not open the gate.")
        size = self.memory.memory[BASE + 13]
        self.assertEqual(
            bytes(self.memory.memory[BASE + 128 : BASE + 128 + size]),
            b"It will stay closed.",
        )

    def test_edited_draft_discards_late_result(self):
        self.memory.request()
        self.controller.tick()
        self.memory.memory[BASE + 9] += 1
        self.executor.finish()
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], RUNNING)
        self.assertEqual(self.memory.memory[BASE + 13], 0)

    def test_reboot_nonce_discards_identical_old_turn(self):
        self.memory.request()
        self.controller.tick()
        self.memory.memory[BASE + 20 : BASE + 24] = bytes(4)
        self.memory.request()
        self.executor.finish()
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], RUNNING)
        self.assertEqual(self.memory.memory[BASE + 13], 0)
        self.executor.finish()
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], READY)

    def test_cancel_discards_late_result(self):
        self.memory.request()
        self.controller.tick()
        self.memory.memory[BASE + 5] = 5
        self.executor.finish()
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], 5)

    def test_external_text_only_delivers_in_paired_receive(self):
        self.controller.queue_external("This is my literal message.")
        self.memory.request("", EXTERNAL, 8)
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], READY)
        self.assertEqual(self.memory.memory[BASE + 14], 255)
        self.assertEqual(self.memory.memory[BASE + 15], 3)
        self.assertEqual(self.executor.calls, [])

    def test_nonpaired_external_request_is_rejected(self):
        self.controller.queue_external("Keep the gate closed.")
        self.memory.request("", EXTERNAL, 3)
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], ERROR)
        self.assertEqual(self.controller.external.qsize(), 1)

    def test_oversized_input_is_not_truncated(self):
        with self.assertRaises(ValueError):
            self.controller.queue_external("a" * 97)
        self.assertTrue(self.controller.external.empty())

    def test_empty_paired_request_does_not_read_empty_memory_slice(self):
        class StrictMemory:
            def __getitem__(inner, address):
                if (
                    isinstance(address, slice)
                    and address.start == address.stop
                ):
                    raise ValueError("PyBoy rejects empty slice")
                return self.memory.memory[address]

            def __setitem__(inner, address, value):
                self.memory.memory[address] = value

        class StrictEmulator:
            memory = StrictMemory()

        self.controller.emulator = StrictEmulator()
        self.controller.queue_external("literal paired draft")
        self.memory.request("", EXTERNAL, 8)
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], READY)
        self.assertEqual(
            self.controller.last_result.text, "literal paired draft"
        )

    def test_bad_protocol_never_writes_heartbeat(self):
        self.memory.memory[BASE + 4] = 2
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 16 : BASE + 20], bytes(4))

    def test_other_thread_cannot_access_emulator(self):
        errors = []

        def tick():
            try:
                self.controller.tick()
            except RuntimeError as error:
                errors.append(str(error))

        worker = threading.Thread(target=tick)
        worker.start()
        worker.join()
        self.assertEqual(len(errors), 1)

    def test_real_http_entry_auth_and_queue_without_auto_commit(self):
        server = paired_server(self.controller, "test-only-secret")
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}"
            with urlopen(endpoint) as response:
                self.assertIn(b'<label for="text">', response.read())
            body = json.dumps({"text": "Keep it closed."}).encode()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(endpoint + "/v1/input", data=body))
            self.assertEqual(error.exception.code, 401)
            error.exception.close()
            request = Request(
                endpoint + "/v1/input",
                data=body,
                headers={"Authorization": "Bearer test-only-secret"},
            )
            with urlopen(request) as response:
                self.assertEqual(response.status, 202)
                self.assertEqual(
                    json.loads(response.read()),
                    {"queued": True, "committed": False},
                )
            self.assertEqual(self.memory.memory[BASE + 5], 0)
            self.memory.request("", EXTERNAL, 8)
            self.controller.tick()
            self.assertEqual(self.memory.memory[BASE + 5], READY)
        finally:
            server.shutdown()
            server.server_close()

    def test_no_picker_signals_error_for_native_authored_fallback(self):
        self.controller.broker = Broker(CONTENT)
        self.memory.request()
        self.controller.tick()
        self.executor.finish()
        self.controller.tick()
        self.assertEqual(self.memory.memory[BASE + 5], ERROR)
        self.assertEqual(self.memory.memory[BASE + 14], 255)
        self.assertEqual(self.memory.memory[BASE + 15], 0)

    def test_picker_uses_distinct_classifier_labels(self):
        self.memory.request()
        self.controller.tick()
        self.executor.finish()
        self.controller.tick()
        self.assertEqual(
            self.picker.call[1]["Keep closed"], "refuse to open the gate"
        )

    def test_compose_context_and_actual_model_provenance(self):
        broker = Broker(CONTENT, provider="ollama", model="test-only-model")
        output = io.BytesIO(
            json.dumps(
                {"done": True, "response": "Keep the gate closed."}
            ).encode()
        )
        with patch(
            "chromatic_demo.playground_bridge.urlopen", return_value=output
        ) as inference:
            result = broker.run(Turn(1, 1, 1, 0, 2, COMPOSE, "ktgc"))
        request = json.loads(inference.call_args.args[0].data)
        self.assertIn("A gate is closed.", request["prompt"])
        self.assertIn("word initials", request["prompt"])
        self.assertIn("refuse to open the gate", request["prompt"])
        self.assertIn("PLAYER", request["prompt"])
        self.assertEqual(result.model_id, "test-only-model")
        self.assertEqual(result.source, 2)
        self.assertEqual(result.intent, 255)

    def test_compose_rejects_oversized_or_incomplete_model_output(self):
        broker = Broker(CONTENT, provider="ollama", model="test-only-model")
        for value in (
            {"done": False, "response": "Keep closed."},
            {"done": True, "response": "a" * 97},
        ):
            with (
                patch(
                    "chromatic_demo.playground_bridge.urlopen",
                    return_value=io.BytesIO(json.dumps(value).encode()),
                ),
                self.assertRaises(ValueError),
            ):
                broker.run(Turn(1, 1, 1, 0, 2, COMPOSE, "ktgc"))

    def test_real_tls_entry_with_reproducibly_generated_test_certificate(self):
        with tempfile.TemporaryDirectory(
            prefix="bridge-test-cert-"
        ) as directory:
            cert = Path(directory) / "cert.pem"
            key = Path(directory) / "key.pem"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                    "-days",
                    "1",
                    "-subj",
                    "/CN=localhost",
                ],
                check=True,
                capture_output=True,
            )
            server = paired_server(
                self.controller, "test-only-secret", cert=cert, key=key
            )
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                endpoint = f"https://127.0.0.1:{server.server_port}/v1/input"
                request = Request(
                    endpoint,
                    data=b'{"text":"Keep it closed."}',
                    headers={"Authorization": "Bearer test-only-secret"},
                )
                context = (
                    ssl._create_unverified_context()
                )  # Synthetic local certificate only.
                with urlopen(request, context=context, timeout=5) as response:
                    self.assertEqual(response.status, 202)
            finally:
                server.shutdown()
                server.server_close()

    def test_duplicate_fields_and_request_framing_are_rejected(self):
        server = paired_server(self.controller, "test-only-secret")
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            cases = [
                (b'{"text":"a","text":"b"}', []),
                (b'{"text":"a"}', ["Content-Length: 12"]),
                (b'{"text":"a"}', ["Transfer-Encoding: chunked"]),
            ]
            for body, extra in cases:
                headers = [
                    "POST /v1/input HTTP/1.1",
                    "Host: localhost",
                    "Authorization: Bearer test-only-secret",
                    f"Content-Length: {len(body)}",
                    *extra,
                    "",
                    "",
                ]
                with socket.create_connection(
                    server.server_address, timeout=5
                ) as connection:
                    connection.sendall("\r\n".join(headers).encode() + body)
                    self.assertIn(
                        b" 400 ", connection.recv(1024).split(b"\r\n")[0]
                    )
            self.assertTrue(self.controller.external.empty())
        finally:
            server.shutdown()
            server.server_close()

    def test_accepted_socket_has_timeout_before_handler_reads(self):
        server = paired_server(self.controller, "test-only-secret")
        client = socket.create_connection(server.server_address, timeout=5)
        try:
            accepted, _ = server.get_request()
            try:
                self.assertEqual(accepted.gettimeout(), 5)
            finally:
                accepted.close()
        finally:
            client.close()
            server.server_close()

    def test_certificate_failure_closes_listening_socket(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        with self.assertRaises(FileNotFoundError):
            paired_server(
                self.controller,
                "test-only-secret",
                port=port,
                cert="/missing/test-only-cert",
                key="/missing/test-only-key",
            )
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))

    def test_lan_requires_tls(self):
        with self.assertRaises(ValueError):
            paired_server(self.controller, "test-only-secret", bind="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
