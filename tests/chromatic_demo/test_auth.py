# SPDX-License-Identifier: GPL-3.0-or-later
"""All identities, credentials, callback codes, and JWKS are synthetic."""

import io
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from chromatic_demo.auth import (
    ISSUER,
    PLAN_SCOPE,
    RESOURCE,
    AuthError,
    Authorization,
    ChatGPTAuth,
    verify_identity,
)


@pytest.fixture
def auth(tmp_path):
    return ChatGPTAuth(tmp_path / "SYNTHETIC_RUNTIME_ONLY")


def synthetic_record():
    return {
        "host_id": "urn:uuid:SYNTHETIC",
        "profile": {
            "client_id": "SYNTHETIC_CLIENT",
            "subject": "SYNTHETIC_SUBJECT",
            "access_token": "SYNTHETIC_ACCESS_NOT_REAL",
            "refresh_token": "SYNTHETIC_REFRESH_NOT_REAL",
            "id_token": "SYNTHETIC_ID_NOT_REAL",
            "scopes": [PLAN_SCOPE, "resource.invoke"],
            "expires_at": time.time() + 3600,
        },
    }


def test_pkce_callback_and_no_token_in_printed_url():
    pending = Authorization(
        "SYNTHETIC_STATE",
        "SYNTHETIC_NONCE",
        "SYNTHETIC_VERIFIER",
        "http://127.0.0.1:1/auth/callback",
    )
    first = parse_qs(urlsplit(pending.url("SYNTHETIC_HOST", {})).query)
    assert first["client_id"] == ["dynamic_agent_client"]
    assert first["resource"] == [RESOURCE]
    assert first["code_challenge_method"] == ["S256"]
    returning = pending.url(
        "SYNTHETIC_HOST", synthetic_record()["profile"], include_hint=False
    )
    assert "id_token_hint" not in returning
    assert "agent_name_hint" not in returning
    valid = "/auth/callback?state=SYNTHETIC_STATE&code=SYNTHETIC_CODE"
    with pytest.raises(AuthError):
        pending.callback(valid)
    assert pending.callback(valid, "SYNTHETIC_CLIENT") == (
        "SYNTHETIC_CLIENT",
        "SYNTHETIC_CODE",
    )
    for bad in (
        valid.replace("SYNTHETIC_STATE", "WRONG_STATE"),
        valid + "&client_id=WRONG_CLIENT",
        "/auth/callback?state=SYNTHETIC_STATE&error=access_denied",
    ):
        with pytest.raises(AuthError):
            pending.callback(bad, "SYNTHETIC_CLIENT")


@pytest.mark.parametrize(
    "mutation", [None, "iss", "aud", "exp", "nonce", "sub", "signature"]
)
def test_real_rsa_signature_and_oidc_validation(mutation):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = dict(
        sub="SYNTHETIC_SUBJECT",
        iss=ISSUER,
        aud="SYNTHETIC_CLIENT",
        nonce="SYNTHETIC_NONCE",
        exp=time.time() + 60,
    )
    if mutation in ("iss", "aud", "nonce"):
        claims[mutation] = "SYNTHETIC_WRONG_VALUE"
    if mutation == "exp":
        claims["exp"] = time.time() - 60
    if mutation == "sub":
        del claims["sub"]
    token = jwt.encode(claims, key, algorithm="RS256")
    checked_key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if mutation == "signature"
        else key
    )
    with patch("jwt.PyJWKClient") as client:
        client.return_value.get_signing_key_from_jwt.return_value.key = (
            checked_key.public_key()
        )
        if mutation:
            with pytest.raises(AuthError):
                verify_identity(token, "SYNTHETIC_CLIENT", "SYNTHETIC_NONCE")
        else:
            assert (
                verify_identity(token, "SYNTHETIC_CLIENT", "SYNTHETIC_NONCE")[
                    "sub"
                ]
                == claims["sub"]
            )


def test_private_atomic_credentials_and_scope_gate(auth):
    record = synthetic_record()
    auth._save(record)
    assert auth.path.stat().st_mode & 0o777 == 0o600
    assert auth.root.stat().st_mode & 0o777 == 0o700
    assert auth.access_token() == "SYNTHETIC_ACCESS_NOT_REAL"
    assert "SYNTHETIC_ACCESS" not in json.dumps(auth.status())
    record["profile"]["scopes"] = ["openid"]
    auth._save(record)
    with pytest.raises(AuthError, match="not granted"):
        auth.access_token()
    auth.path.chmod(0o644)
    with pytest.raises(AuthError, match="owner-only"):
        auth.status()
    with pytest.raises(AuthError, match="outside"):
        ChatGPTAuth(Path(__file__).parents[1] / "credentials")


def test_refresh_rotation_account_rejection_and_logout(auth):
    record = synthetic_record()
    record["profile"]["expires_at"] = time.time() - 1
    auth._save(record)
    tokens = dict(
        access_token="SYNTHETIC_REPLACEMENT",
        token_type="Bearer",
        refresh_token="SYNTHETIC_ROTATED",
        expires_in=3600,
        scope=PLAN_SCOPE + " resource.invoke",
    )
    with patch("chromatic_demo.auth.request_json", return_value=tokens) as req:
        assert auth.access_token() == "SYNTHETIC_REPLACEMENT"
        assert req.call_args.kwargs["form"]["grant_type"] == "refresh_token"
        assert "scope" not in req.call_args.kwargs["form"]
    assert auth._read()["profile"]["refresh_token"] == "SYNTHETIC_ROTATED"
    with patch(
        "chromatic_demo.auth.verify_identity", return_value={"sub": "WRONG"}
    ):
        with pytest.raises(AuthError, match="account changed"):
            auth._tokens(
                auth._read(), dict(tokens, id_token="SYNTHETIC"), "nonce"
            )
    assert auth.access_token() == "SYNTHETIC_REPLACEMENT"
    with patch("chromatic_demo.auth.urlopen", side_effect=OSError):
        with pytest.raises(AuthError, match="unconfirmed"):
            auth.logout()
    assert auth._read()["profile"] == {
        "client_id": "SYNTHETIC_CLIENT",
        "subject": "SYNTHETIC_SUBJECT",
    }


def test_account_model_catalog_filters_and_rejects(auth):
    auth._save(synthetic_record())
    data = {
        "models": [
            dict(
                slug="SYNTHETIC_VISIBLE",
                display_name="Synthetic",
                visibility="list",
            ),
            dict(slug="SYNTHETIC_HIDDEN", visibility="hide"),
        ]
    }
    with patch("chromatic_demo.auth.request_json", return_value=data):
        assert auth.models() == [
            dict(slug="SYNTHETIC_VISIBLE", display_name="Synthetic")
        ]
    with patch("chromatic_demo.auth.request_json", return_value={"data": []}):
        with pytest.raises(AuthError, match="catalog"):
            auth.models()


def test_no_browser_login_uses_issued_client_and_never_opens_browser(
    auth, capsys
):
    server = MagicMock(server_port=12345)
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    handler_class = []

    def serve(address, handler):
        assert address == ("127.0.0.1", 0)
        handler_class.append(handler)
        return server

    def callback():
        url = capsys.readouterr().out.split("browser: ", 1)[1].strip()
        query = parse_qs(urlsplit(url).query)
        handler = MagicMock(
            path="/auth/callback?state="
            + query["state"][0]
            + "&code=SYNTHETIC_CODE&client_id=SYNTHETIC_ISSUED",
            wfile=io.BytesIO(),
        )
        handler_class[0].do_GET(handler)

    server.handle_request.side_effect = callback
    data = dict(
        access_token="SYNTHETIC_ACCESS",
        refresh_token="SYNTHETIC_REFRESH",
        id_token="SYNTHETIC_ID",
        token_type="Bearer",
        expires_in=3600,
        scope=PLAN_SCOPE + " resource.invoke",
    )
    with (
        patch("chromatic_demo.auth.HTTPServer", side_effect=serve),
        patch("chromatic_demo.auth.webbrowser.open") as browser,
        patch("chromatic_demo.auth.request_json", return_value=data) as req,
        patch(
            "chromatic_demo.auth.verify_identity",
            return_value={"sub": "SYNTHETIC_SUBJECT"},
        ),
    ):
        assert auth.login(open_browser=False, timeout=1)["plan_usage"]
        browser.assert_not_called()
        form = req.call_args.kwargs["form"]
        assert form["client_id"] == "SYNTHETIC_ISSUED"
        assert form["code"] == "SYNTHETIC_CODE"
        assert "client_secret" not in form
