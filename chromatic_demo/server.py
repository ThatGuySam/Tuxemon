# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in paired dialogue endpoint for a future Wi-Fi handheld/MCU client."""

import argparse
import hmac
import ipaddress
import json
import os
import secrets
import ssl
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .providers import (
    ChatGPTProvider,
    OllamaProvider,
    display_text,
)
from .rom import INTENTS, authored_dialogue

MAX_BODY = 8192


class DialogueServer(HTTPServer):
    def get_request(self):
        request, address = super().get_request()
        request.settimeout(10)
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


def pairing_secret(path: Path, repo: Path) -> str:
    """Generate once or read protected pairing material without logging it."""
    path = path.expanduser().absolute()
    source = Path(__file__).resolve().parents[1]
    if (
        any(
            path.resolve().is_relative_to(root.resolve())
            for root in (source, repo)
        )
        or path.is_symlink()
    ):
        raise ValueError("Pairing file must be outside the source tree")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("Pairing directory must have owner-only access")
    if not path.exists():
        fd, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(secrets.token_urlsafe(32) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("Pairing file must have owner-only access")
    secret = path.read_text().strip()
    if not 32 <= len(secret) <= 128 or not all(
        33 <= ord(c) <= 126 for c in secret
    ):
        raise ValueError("Invalid pairing file")
    return secret


def create_server(
    repo: Path,
    *,
    provider_name="offline",
    model=None,
    bind="127.0.0.1",
    port=0,
    pairing_file=None,
    tls_cert=None,
    tls_key=None,
    provider=None,
) -> HTTPServer:
    """Prepare a serial HTTP server; the caller owns serve/close lifecycle."""
    try:
        loopback = ipaddress.ip_address(bind).is_loopback
    except ValueError:
        loopback = bind == "localhost"
    if bool(tls_cert) != bool(tls_key) or (not loopback and not tls_cert):
        raise ValueError("Nonloopback bind requires TLS certificate and key")
    if provider_name not in ("offline", "ollama", "chatgpt"):
        raise ValueError("Unknown provider")
    if provider_name != "offline" and not model:
        raise ValueError("Live providers require an explicit model")
    contexts = authored_dialogue(repo)
    if provider is None and provider_name != "offline":
        provider = (
            OllamaProvider(model)
            if provider_name == "ollama"
            else ChatGPTProvider(model)
        )
    file = Path(
        pairing_file
        or (
            Path.home()
            / ".local/share/tuxemon-chromatic-network/pairing.secret"
        )
    )
    secret = pairing_secret(file, repo)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(10)
            super().setup()

        def log_message(self, *args):
            pass

        def send_error(self, code, message=None, explain=None):
            self.respond(code, {"error": "request_rejected"})

        def respond(self, status, value):
            content = json.dumps(value, ensure_ascii=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(content)
            self.close_connection = True

        def do_POST(self):
            auth = self.headers.get_all("Authorization", [])
            if len(auth) != 1 or not hmac.compare_digest(
                auth[0].encode(), ("Bearer " + secret).encode()
            ):
                self.respond(401, {"error": "unauthorized"})
                return
            if self.path != "/v1/dialogue":
                self.respond(404, {"error": "unknown_path"})
                return
            lengths = self.headers.get_all("Content-Length", [])
            if (
                self.headers.get("Transfer-Encoding")
                or len(lengths) != 1
                or not lengths[0].isascii()
                or not lengths[0].isdigit()
            ):
                self.respond(400, {"error": "invalid_length"})
                return
            if len(lengths[0]) > 6 or int(lengths[0]) > MAX_BODY:
                self.respond(413, {"error": "body_too_large"})
                return
            length = int(lengths[0])
            try:
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("Incomplete body")
                value = json.loads(body, object_pairs_hook=unique_object)
                if not isinstance(value, dict) or set(value) != {
                    "request_id",
                    "intent",
                }:
                    raise ValueError("Unexpected schema")
                request_id, intent = value["request_id"], value["intent"]
                if (
                    not isinstance(request_id, str)
                    or not 1 <= len(request_id) <= 64
                    or not all(32 <= ord(c) <= 126 for c in request_id)
                    or not isinstance(intent, str)
                    or intent not in INTENTS
                ):
                    raise ValueError("Invalid intent or request ID")
            except (ValueError, TypeError, OSError, RecursionError):
                self.respond(400, {"error": "invalid_request"})
                return
            text, source, reason = contexts[intent], "authored", None
            fallback = provider_name == "offline"
            if provider_name != "offline":
                try:
                    text = provider.reply(
                        "Professor", intent, contexts[intent]
                    )
                    text = display_text(text)
                    source = provider_name
                except Exception:
                    text, fallback, reason = (
                        contexts[intent],
                        True,
                        "provider_unavailable",
                    )
            self.respond(
                200,
                dict(
                    request_id=request_id,
                    text=display_text(text),
                    provider=provider_name,
                    source=source,
                    fallback=fallback,
                    reason=reason,
                ),
            )

    server = DialogueServer((bind, port), Handler)
    if tls_cert:
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(tls_cert, tls_key)
            server.socket = context.wrap_socket(
                server.socket, server_side=True, do_handshake_on_connect=False
            )
        except Exception:
            server.server_close()
            raise
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--provider",
        choices=["offline", "ollama", "chatgpt"],
        default="offline",
    )
    parser.add_argument("--model")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--pairing-file", type=Path)
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    args = parser.parse_args(argv)
    try:
        with create_server(
            args.repo,
            provider_name=args.provider,
            model=args.model,
            bind=args.bind,
            port=args.port,
            pairing_file=args.pairing_file,
            tls_cert=args.tls_cert,
            tls_key=args.tls_key,
        ) as server:
            scheme = "https" if args.tls_cert else "http"
            print(
                json.dumps(
                    dict(
                        listener=f"{scheme}://{args.bind}:{server.server_port}",
                        provider=args.provider,
                        model=args.model,
                    )
                ),
                flush=True,
            )
            server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
