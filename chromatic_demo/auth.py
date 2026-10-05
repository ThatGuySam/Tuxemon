# SPDX-License-Identifier: GPL-3.0-or-later
"""Public Sign in with ChatGPT flow; real account access is opt-in."""

import argparse
import base64
import fcntl
import hashlib
import json
import math
import os
import secrets
import tempfile
import time
import uuid
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ISSUER = "https://auth.openai.com"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + PLAN_SCOPE


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


urlopen = build_opener(NoRedirect()).open


class AuthError(RuntimeError):
    """Sign-in or grant unavailable; no API billing fallback."""


def request_json(url, *, form=None, headers=None):
    data = urlencode(form).encode() if form is not None else None
    try:
        with urlopen(
            Request(url, data=data, headers=headers or {}), timeout=10
        ) as response:
            content = response.read(65537)
            if len(content) > 65536:
                raise ValueError("Response too large")
            return json.loads(content)
    except Exception:
        raise AuthError("Authentication service request failed.") from None


def verify_identity(token, client_id, nonce=None):
    try:
        import jwt

        key = (
            jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json", timeout=10)
            .get_signing_key_from_jwt(token)
            .key
        )
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=ISSUER,
            options={"require": ["sub", "exp", "iss", "aud"]},
        )
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("Missing subject")
        if nonce is not None and claims.get("nonce") != nonce:
            raise ValueError("Nonce mismatch")
        return claims
    except ImportError:
        raise AuthError("Install companion PyJWT[crypto] requirements.")
    except Exception:
        raise AuthError("ID token validation failed.") from None


@dataclass(frozen=True)
class Authorization:
    state: str
    nonce: str
    verifier: str
    redirect_uri: str

    def url(self, host_id, profile, include_hint=True):
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(self.verifier.encode()).digest()
            )
            .decode()
            .rstrip("=")
        )
        args = dict(
            client_id=profile.get("client_id", "dynamic_agent_client"),
            ext_agent_host_id=host_id,
            response_type="code",
            redirect_uri=self.redirect_uri,
            resource=RESOURCE,
            scope=SCOPES,
            state=self.state,
            nonce=self.nonce,
            code_challenge=challenge,
            code_challenge_method="S256",
        )
        if profile.get("client_id"):
            if include_hint and profile.get("id_token"):
                args["id_token_hint"] = profile["id_token"]
        else:
            args["agent_name_hint"] = "Tuxemon Chromatic Prototype"
        return ISSUER + "/api/accounts/authorize?" + urlencode(args)

    def callback(self, path, prior_client=None):
        parsed = urlsplit(path)
        query = parse_qs(parsed.query)
        if parsed.path != "/auth/callback":
            raise AuthError("Unexpected callback path.")
        if query.get("state") != [self.state]:
            raise AuthError("Callback state mismatch.")
        if "error" in query:
            raise AuthError("Authorization declined or unavailable.")
        clients = query.get("client_id", [prior_client])
        codes = query.get("code", [None])
        if len(clients) != 1 or len(codes) != 1:
            raise AuthError("Ambiguous callback parameters.")
        client, code = clients[0], codes[0]
        if not code or not client or client == "dynamic_agent_client":
            raise AuthError("Incomplete registration callback.")
        if prior_client and client != prior_client:
            raise AuthError("Callback client mismatch.")
        return client, code


class ChatGPTAuth:
    def __init__(self, runtime_dir=None):
        self.root = (
            Path(
                runtime_dir
                or (Path.home() / ".local/share/tuxemon-chromatic-auth")
            )
            .expanduser()
            .absolute()
        )
        source = Path(__file__).resolve().parents[1]
        if self.root.is_symlink() or self.root.resolve().is_relative_to(
            source
        ):
            raise AuthError("Credentials must live outside the source tree.")
        self.path = self.root / "credentials.json"

    def _read(self):
        if not self.path.exists():
            return {"host_id": "urn:uuid:" + str(uuid.uuid4()), "profile": {}}
        if self.path.is_symlink() or self.path.stat().st_mode & 0o077:
            raise AuthError("Credential file must have owner-only access.")
        try:
            record = json.loads(self.path.read_text())
            if not isinstance(record["host_id"], str) or not isinstance(
                record["profile"], dict
            ):
                raise ValueError("Invalid credential record")
            return record
        except (ValueError, TypeError, KeyError):
            raise AuthError("Invalid credential record.") from None

    def _save(self, record):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        fd, name = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(record, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _tokens(self, record, data, nonce=None):
        previous = record["profile"]
        identity = (
            verify_identity(data.get("id_token"), previous["client_id"], nonce)
            if nonce is not None or data.get("id_token")
            else {"sub": previous["subject"]}
        )
        if previous.get("subject", identity["sub"]) != identity["sub"]:
            raise AuthError(
                "Signed-in account changed; credentials preserved."
            )
        if not data.get("access_token") or data.get("token_type") != "Bearer":
            raise AuthError("Invalid token response.")
        try:
            expires_in = float(data["expires_in"])
            if not math.isfinite(expires_in) or expires_in <= 0:
                raise ValueError("Invalid lifetime")
        except (KeyError, ValueError, TypeError):
            raise AuthError("Invalid token expiry.") from None
        profile = dict(
            previous,
            subject=identity["sub"],
            access_token=data["access_token"],
            id_token=data.get("id_token", previous.get("id_token")),
            refresh_token=data.get(
                "refresh_token", previous.get("refresh_token")
            ),
            scopes=(
                data["scope"].split()
                if "scope" in data
                else previous.get("scopes", [])
            ),
            expires_at=time.time() + expires_in,
        )
        record["profile"] = profile
        if profile["expires_at"] <= time.time():
            raise AuthError("Invalid token expiry.")
        self._save(record)

    def login(self, open_browser=True, timeout=180):
        if not 1 <= timeout <= 180:
            raise AuthError("Login timeout must be between 1 and 180 seconds.")
        record = self._read()
        self._save(record)
        result = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                try:
                    value = pending.callback(
                        handler.path, record["profile"].get("client_id")
                    )
                    result.append(value)
                    handler.send_response(200)
                except AuthError:
                    handler.send_response(400)
                    query = parse_qs(urlsplit(handler.path).query)
                    if (
                        query.get("state") == [pending.state]
                        and "error" in query
                    ):
                        result.append(AuthError("Authorization declined."))
                handler.end_headers()
                handler.wfile.write(b"Return to the Tuxemon companion.")

            def log_message(handler, *args):
                pass

            def setup(handler):
                handler.request.settimeout(2)
                super().setup()

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            server.timeout = 1
            pending = Authorization(
                secrets.token_urlsafe(32),
                secrets.token_urlsafe(32),
                secrets.token_urlsafe(48),
                f"http://127.0.0.1:{server.server_port}/auth/callback",
            )
            url = pending.url(
                record["host_id"], record["profile"], include_hint=open_browser
            )
            if open_browser and not webbrowser.open(url):
                raise AuthError("Could not open the sign-in browser.")
            if not open_browser:
                print(
                    "Open this sign-in URL in your browser:", url, flush=True
                )
            deadline = time.monotonic() + timeout
            while not result and time.monotonic() < deadline:
                server.handle_request()
            if not result:
                raise AuthError("Sign-in timed out or was declined.")
        if isinstance(result[0], AuthError):
            raise result[0]
        client_id, code = result[0]
        record["profile"]["client_id"] = client_id
        self._save(record)
        data = request_json(
            TOKEN_URL,
            form=dict(
                grant_type="authorization_code",
                client_id=client_id,
                code=code,
                code_verifier=pending.verifier,
                redirect_uri=pending.redirect_uri,
                resource=RESOURCE,
            ),
        )
        self._tokens(record, data, pending.nonce)
        return self.status()

    def access_token(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        lock_path = self.root / "refresh.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._access_token()

    def _access_token(self):
        record = self._read()
        profile = record["profile"]
        if not profile.get("access_token"):
            raise AuthError("Sign in with ChatGPT first.")
        if profile["expires_at"] < time.time() + 60:
            if not profile.get("refresh_token"):
                raise AuthError("Session expired; sign in again.")
            data = request_json(
                TOKEN_URL,
                form=dict(
                    grant_type="refresh_token",
                    client_id=profile["client_id"],
                    refresh_token=profile["refresh_token"],
                    resource=RESOURCE,
                ),
            )
            self._tokens(record, data)
            profile = record["profile"]
        if not {PLAN_SCOPE, "resource.invoke"}.issubset(profile["scopes"]):
            raise AuthError("ChatGPT plan usage was not granted.")
        return profile["access_token"]

    def models(self):
        data = request_json(
            RESOURCE + "/models",
            headers={"Authorization": "Bearer " + self.access_token()},
        )
        try:
            choices = data["models"]
            if not isinstance(choices, list):
                raise ValueError("Missing model list")
            result = [
                {"slug": item["slug"], "display_name": item["display_name"]}
                for item in choices
                if item["visibility"] == "list"
            ]
            if any(
                not isinstance(v, str) or not v
                for item in result
                for v in item.values()
            ):
                raise ValueError("Invalid model")
            return result
        except (TypeError, KeyError, ValueError):
            raise AuthError("Unexpected account model catalog.") from None

    def status(self):
        profile = self._read()["profile"]
        return dict(
            connected=bool(profile.get("access_token")),
            plan_usage=PLAN_SCOPE in profile.get("scopes", []),
            expires_at=profile.get("expires_at"),
        )

    def logout(self):
        record = self._read()
        profile = record["profile"]
        failed = False
        if profile.get("refresh_token"):
            try:
                request = Request(
                    ISSUER + "/api/accounts/oauth/revoke",
                    data=urlencode(
                        dict(
                            token=profile["refresh_token"],
                            token_type_hint="refresh_token",
                            client_id=profile["client_id"],
                        )
                    ).encode(),
                )
                with urlopen(request, timeout=10):
                    pass
            except Exception:
                failed = True
        record["profile"] = {
            key: profile[key]
            for key in ("client_id", "subject")
            if key in profile
        }
        self._save(record)
        if failed:
            raise AuthError(
                "Signed out locally; remote revocation unconfirmed. "
                "Disconnect in ChatGPT Settings."
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["login", "models", "status", "logout"]
    )
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--no-browser", "--no-open", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.timeout <= 180:
            parser.error("timeout must be between 1 and 180 seconds")
        auth = ChatGPTAuth(args.runtime_dir)
        value = (
            auth.login(not args.no_browser, args.timeout)
            if args.command == "login"
            else getattr(auth, args.command)()
        )
        print(json.dumps(value))
    except AuthError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
