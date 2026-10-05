# SPDX-License-Identifier: GPL-3.0-or-later
"""Run one explicitly selected Chromatic USB demo through the public MCP client."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, TextIO


class Session:
    def __init__(
        self, process: subprocess.Popen[str], journal: TextIO
    ) -> None:
        self.process, self.journal = process, journal
        self.pending: dict[str, Any] | None = None
        self.interrupted = False

    def read(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(
                "Public wrapper closed unexpectedly; original outcome unverified."
            )
        self.journal.write(line)
        self.journal.flush()
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RuntimeError("Invalid public wrapper response.")
        return value

    def send(self, value: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.journal.write(json.dumps({"clientRequest": value}) + "\n")
        self.journal.flush()
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        mutating = tool == "play" or arguments.get("command") == "list_devices"
        if mutating and (self.interrupted or self.pending):
            raise RuntimeError(
                "Interrupted or unresolved: no new device action started."
            )
        request_id = str(uuid.uuid4())
        if mutating:
            self.pending = {"requestId": arguments["requestId"]}
        self.send({"id": request_id, "tool": tool, "arguments": arguments})
        while True:
            event = self.read()
            if event.get("id") != request_id:
                continue
            if event.get("event") == "accepted":
                content = event["result"].get("structuredContent", {})
                if self.pending and content.get("operationId"):
                    self.pending = {"operationId": content["operationId"]}
                print(
                    f"{tool}: accepted {content.get('operationId', '')}",
                    flush=True,
                )
            if event.get("event") not in {"result", "unknown", "error"}:
                continue
            result = event.get("result") or {}
            content = result.get("structuredContent") or {}
            if content.get("operationId") and mutating:
                self.pending = {"operationId": content["operationId"]}
            if (
                content.get("state") in {"succeeded", "failed"}
                or content.get("operationStarted") is False
            ):
                self.pending = None
            elif event.get("completion") == "not-dispatched":
                self.pending = None
            elif event.get("event") == "error" and "pendingOperation" in event:
                self.pending = event["pendingOperation"]
            print(
                f"{tool}: {content.get('state', event.get('completion', event['event']))}",
                flush=True,
            )
            if (
                event.get("error")
                or result.get("isError")
                or event.get("completion") == "unverified"
            ):
                error = content.get("error") or {}
                message = (
                    error.get("message")
                    if isinstance(error, dict)
                    else str(error)
                )
                raise RuntimeError(
                    message
                    or event.get("error")
                    or "Original operation unverified; inspect journal."
                )
            return content

    def close(self) -> None:
        while self.pending:
            print(
                "Retaining foreground owner; reading original operation status.",
                flush=True,
            )
            time.sleep(1)
            query = {
                key: self.pending[key]
                for key in ("operationId", "requestId")
                if key in self.pending
            }
            try:
                self.call("device", {"command": "operation_status", **query})
            except RuntimeError as error:
                print(str(error), flush=True)
        self.send({"id": "done", "close": True})
        while True:
            event = self.read()
            if event.get("event") == "closed":
                if event.get("pendingOperation") or event.get("closeDeferred"):
                    raise RuntimeError(
                        "Wrapper closed with an unresolved operation; preserve journal."
                    )
                break
        self.process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plugin", "repo", "rom"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument(
        "--player", type=int, choices=range(1, 9), required=True
    )
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args()
    if not 0.1 <= args.seconds <= 120:
        parser.error("--seconds must be between 0.1 and 120")
    repo, rom, plugin = (
        args.repo.resolve(strict=True),
        args.rom.resolve(strict=True),
        args.plugin.resolve(strict=True),
    )
    if not rom.is_relative_to(repo):
        parser.error("ROM must be inside the exact authorized repository")
    build = (repo / "build").resolve()
    journal = (
        args.journal or build / "chromatic" / f"usb-{uuid.uuid4()}.jsonl"
    ).resolve()
    if not journal.is_relative_to(build):
        parser.error("Journal must be under the repository build directory")
    journal.parent.mkdir(parents=True, exist_ok=True)
    stderr_path = journal.with_suffix(".stderr.txt")
    with (
        os.fdopen(
            os.open(journal, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600),
            "w",
            encoding="utf-8",
        ) as log,
        os.fdopen(
            os.open(stderr_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600),
            "w",
            encoding="utf-8",
        ) as stderr,
    ):
        process = subprocess.Popen(
            [
                "node",
                str(plugin / "scripts/device-mcp.mjs"),
                "--package",
                str(plugin),
                "--workspace",
                str(repo),
                "--jsonl",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            bufsize=1,
        )
        session = Session(process, log)

        def interrupted(signum: int, frame: Any) -> None:
            session.interrupted = True
            print(
                "Interrupted: preserving the original owner until settlement.",
                flush=True,
            )

        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(signum, interrupted)
        try:
            ready = session.read()
            session.pending = ready.get("pendingOperation")
            if ready.get("event") != "ready" or ready.get("pendingOperation"):
                raise RuntimeError(
                    "Public wrapper did not report an idle ready session."
                )
            inspected = session.call("rom_inspect", {"romPath": str(rom)})
            if (
                not inspected.get("valid")
                or Path(inspected["path"]).resolve() != rom
            ):
                raise RuntimeError("Exact ROM failed public inspection.")
            status = session.call("device", {"command": "status"})
            if (
                status.get("retainedReservation")
                or status.get("activeOperation")
                or not status.get("acceptingOperations")
            ):
                raise RuntimeError(
                    "Device service has a reservation or cannot admit a new operation."
                )
            discovery = session.call(
                "device",
                {"command": "list_devices", "requestId": str(uuid.uuid4())},
            )["result"]
            for notice in discovery.get("diagnostics", []):
                print(
                    f"Discovery: {notice.get('message', 'See journal diagnostics')}",
                    flush=True,
                )
            matches = [
                device
                for device in discovery["devices"]
                if device.get("player") == args.player
            ]
            if len(matches) != 1 or not matches[0].get("deviceToken"):
                raise RuntimeError(
                    "Requested player is absent or ambiguous; no play started."
                )
            played = session.call(
                "play",
                {
                    "deviceToken": matches[0]["deviceToken"],
                    "romPath": inspected["path"],
                    "expectedSizeBytes": inspected["sizeBytes"],
                    "expectedSha256": inspected["sha256"],
                    "requestId": str(uuid.uuid4()),
                    "confirm": True,
                    "durationSeconds": args.seconds,
                    "saveMode": "none",
                },
            )
            if (
                played.get("state") != "succeeded"
                or played.get("success") is not True
            ):
                raise RuntimeError(
                    "Play did not report a successful settled operation."
                )
            report = played.get("result", {})
            print(
                f"Play completion: {report.get('completion', 'unknown')}; requested seconds: {report.get('durationSeconds', 'unknown')}"
            )
        except Exception:
            try:
                session.close()
            except Exception as error:
                print(
                    f"Cleanup unverified: {error}; preserve {journal}",
                    flush=True,
                )
            raise
        else:
            session.close()
    print(f"Journal: {journal}")


if __name__ == "__main__":
    main()
