# SPDX-License-Identifier: GPL-3.0-or-later
"""Local HTTP integration with real authored facts and SYNTHETIC pairing."""

import http.client
import ipaddress
import json
import ssl
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from chromatic_demo import rom
from chromatic_demo.providers import ProviderError
from chromatic_demo.rom import authored_dialogue
from chromatic_demo.server import MAX_BODY, create_server, pairing_secret

REPO = Path(rom.__file__).resolve().parents[1]
SYNTHETIC_SECRET = "SYNTHETIC_TEST_PAIRING_SECRET_NOT_REAL_123456"


class SyntheticProvider:
    def __init__(self, failure=False):
        self.failure = failure
        self.calls = []

    def reply(self, npc, intent, context):
        self.calls.append((npc, intent, context))
        if self.failure:
            raise ProviderError("SYNTHETIC_SECRET_MUST_NEVER_APPEAR")
        return "SYNTHETIC_TEST_REPLY"


@pytest.fixture
def run_server(tmp_path):
    servers = []

    def start(provider_name="offline", provider=None):
        file = tmp_path / (str(len(servers)) + ".pairing")
        file.write_text(SYNTHETIC_SECRET)
        file.chmod(0o600)
        server = create_server(
            REPO,
            provider_name=provider_name,
            provider=provider,
            model="SYNTHETIC_MODEL" if provider_name != "offline" else None,
            pairing_file=file,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return server

    yield start
    for server, thread in servers:
        server.shutdown()
        thread.join(timeout=4)
        server.server_close()


def post(server, value, *, authenticated=True, path="/v1/dialogue"):
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=2
    )
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["Authorization"] = "Bearer " + SYNTHETIC_SECRET
    connection.request("POST", path, body, headers)
    response = connection.getresponse()
    result = response.status, json.loads(response.read())
    connection.close()
    return result


def test_offline_real_authored_exact_request_id(run_server):
    server = run_server()
    for intent, context in authored_dialogue(REPO).items():
        status, result = post(
            server, dict(request_id="SYNTHETIC_ID", intent=intent)
        )
        assert status == 200
        assert result["request_id"] == "SYNTHETIC_ID"
        assert (
            result["provider"] == "offline" and result["source"] == "authored"
        )
        assert result["fallback"] is True and result["reason"] is None
        assert 1 <= len(result["text"]) <= 320
        assert all(32 <= ord(c) <= 126 for c in result["text"])
        assert result["text"] == " ".join(context.split())[:320]


def test_authorization_rejected_before_body_read(run_server):
    server = run_server()
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=1
    )
    connection.putrequest("POST", "/v1/dialogue")
    connection.putheader("Content-Length", str(MAX_BODY))
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 401
    assert json.loads(response.read()) == {"error": "unauthorized"}
    connection.close()


@pytest.mark.parametrize(
    "value",
    [
        b"invalid JSON",
        b'{"request_id":"SYNTHETIC","request_id":"DUPLICATE","intent":"greet"}',
        [],
        {},
        {"request_id": "SYNTHETIC", "intent": "unknown"},
        {"request_id": "SYNTHETIC", "intent": "greet", "context": "injection"},
        {"request_id": "x" * 65, "intent": "greet"},
        {"request_id": "\u00e9", "intent": "greet"},
        {"request_id": "", "intent": "greet"},
        {"request_id": "\x00", "intent": "greet"},
        {"request_id": 1, "intent": "greet"},
        {"request_id": "SYNTHETIC", "intent": []},
    ],
)
def test_invalid_request_and_schema(run_server, value):
    assert post(run_server(), value)[0] == 400


def test_paths_and_oversized_body(run_server):
    server = run_server()
    assert post(server, {}, path="/v1/dialogue?secret=never_log")[0] == 404
    assert post(server, b"x" * (MAX_BODY + 1))[0] == 413


@pytest.mark.parametrize("length", [None, "-1", "+2", "2.0", "nan"])
def test_missing_or_weird_lengths(run_server, length):
    server = run_server()
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=2
    )
    connection.putrequest("POST", "/v1/dialogue")
    connection.putheader("Authorization", "Bearer " + SYNTHETIC_SECRET)
    if length is not None:
        connection.putheader("Content-Length", length)
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 400
    response.read()
    connection.close()


@pytest.mark.parametrize("header", ["Transfer-Encoding", "Content-Length"])
def test_chunked_and_duplicate_content_lengths_rejected(run_server, header):
    server = run_server()
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=2
    )
    connection.putrequest("POST", "/v1/dialogue")
    connection.putheader("Authorization", "Bearer " + SYNTHETIC_SECRET)
    connection.putheader("Content-Length", "2")
    connection.putheader(
        header, "chunked" if header == "Transfer-Encoding" else "2"
    )
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 400
    response.read()
    connection.close()


def test_provider_success_and_sanitized_fallback(run_server):
    for failure in (False, True):
        provider = SyntheticProvider(failure)
        server = run_server("ollama", provider)
        status, result = post(
            server, dict(request_id="SYNTHETIC_ID", intent="greet")
        )
        assert status == 200
        assert provider.calls == [
            ("Professor", "greet", authored_dialogue(REPO)["greet"])
        ]
        assert result["fallback"] is failure
        assert result["source"] == ("authored" if failure else "ollama")
        assert result["reason"] == (
            "provider_unavailable" if failure else None
        )
        assert "SYNTHETIC_SECRET_MUST_NEVER_APPEAR" not in json.dumps(result)


def test_pairing_protection_and_live_tls_requirements(tmp_path):
    file = tmp_path / "private-pairing"
    secret = pairing_secret(file, REPO)
    assert pairing_secret(file, REPO) == secret
    assert file.stat().st_mode & 0o777 == 0o600
    file.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        pairing_secret(file, REPO)
    with pytest.raises(ValueError, match="outside"):
        pairing_secret(REPO / "SYNTHETIC_FORBIDDEN_PAIRING", REPO)
    with pytest.raises(ValueError, match="TLS"):
        create_server(REPO, bind="0.0.0.0", pairing_file=file)
    with pytest.raises(ValueError, match="explicit model"):
        create_server(REPO, provider_name="chatgpt", pairing_file=file)


def test_tls_local_certificate_handshake_and_dialogue(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "SYNTHETIC_TEST_ONLY")]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(minutes=5))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = (
        tmp_path / "SYNTHETIC_CERT.pem",
        tmp_path / "SYNTHETIC_KEY.pem",
    )
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_file.chmod(0o600)
    file = tmp_path / "SYNTHETIC_PAIRING"
    file.write_text(SYNTHETIC_SECRET)
    file.chmod(0o600)
    server = create_server(
        REPO, pairing_file=file, tls_cert=cert_file, tls_key=key_file
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        context = ssl.create_default_context(cafile=str(cert_file))
        client = http.client.HTTPSConnection(
            "127.0.0.1", server.server_port, timeout=2, context=context
        )
        client.request(
            "POST",
            "/v1/dialogue",
            json.dumps(dict(request_id="SYNTHETIC_TLS_ID", intent="farewell")),
            {"Authorization": "Bearer " + SYNTHETIC_SECRET},
        )
        response = client.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["request_id"] == "SYNTHETIC_TLS_ID"
        client.close()
    finally:
        server.shutdown()
        thread.join(timeout=4)
        server.server_close()
