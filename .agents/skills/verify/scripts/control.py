#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and drive isolated Chromatic ROM verification bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "build/chromatic/verification"
PYTHON = ROOT / "venv/chromatic/bin/python"
PICKER_PYTHON = ROOT / "venv/chromatic-picker/bin/python"


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def run_path(value):
    path = Path(value).resolve()
    if not path.is_relative_to(BASE.resolve()) or path == BASE.resolve():
        raise ValueError(
            "Run must be an owned child of build/chromatic/verification"
        )
    record = json.loads((path / "run.json").read_text())
    if record.get("owner") != "chromatic-project-verify" or record.get(
        "repo"
    ) != str(ROOT):
        raise ValueError("Not a verification run created by this helper")
    return path, record


def execute(run, label, command, timeout=600, allow_failure=False):
    started_at = datetime.now(timezone.utc).isoformat()
    child_env = os.environ.copy()
    child_env.pop("PYTHONOPTIMIZE", None)
    try:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=child_env,
        )
    except subprocess.TimeoutExpired as error:

        def decoded(value):
            return (
                value.decode(errors="replace")
                if isinstance(value, bytes)
                else value or ""
            )

        result = subprocess.CompletedProcess(
            command,
            124,
            decoded(error.stdout),
            decoded(error.stderr)
            + f"\nOwned verification child exceeded {timeout} seconds.\n",
        )
    (run / (label + ".stdout.txt")).write_text(result.stdout)
    (run / (label + ".stderr.txt")).write_text(result.stderr)
    write(
        run / (label + ".command.json"),
        {
            "command": [str(p) for p in command],
            "exit_code": result.returncode,
            "started_at_utc": started_at,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(result.stdout, end="")
    if result.returncode and not allow_failure:
        print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(
            f"{label} failed with exit {result.returncode}; evidence retained at {run}"
        )
    return result


def doctor(run):
    write(
        run / "doctor.json",
        {
            "ready": False,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    bundle = run / "rom"
    provenance = json.loads(
        (bundle / "playground-provenance.json").read_text()
    )
    digest = hashlib.sha256(
        (bundle / "playground.gbc").read_bytes()
    ).hexdigest()
    expected = provenance.get("rom_sha256")
    if expected != digest:
        raise ValueError("ROM digest differs from its build provenance")
    code = """import sys,json
from pathlib import Path
from pyboy import PyBoy
b=Path(sys.argv[1]); symbols={}
for line in (b/'playground.noi').read_text().splitlines():
 w=line.split()
 if len(w)==3 and w[0]=='DEF': symbols[w[1]]=int(w[2],16)
p=PyBoy(str(b/'playground.gbc'),window='null',sound_emulated=False)
try:
 p.set_emulation_speed(0);p.tick(180)
 assert p.memory[symbols['_phase']]==0,'ROM did not reach WORLD'
 assert bytes(p.memory[0xC800:0xC805])==b'TXMB\\x01','Mailbox handshake invalid'
 assert p.memory[0xFF40]&0x80,'LCD is disabled'
 assert any(min(v)<100 for v in p.screen.image.convert('RGB').get_flattened_data()),'Booted screen is blank'
 print(json.dumps({'ready':True,'phase':'WORLD','transport':'owned_headless_pyboy','saves_written':False}))
finally:p.stop(save=False)
"""
    execute(run, "doctor", [PYTHON, "-c", code, bundle])
    write(
        run / "doctor.json",
        {
            "ready": True,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "rom_sha256": digest,
            "bundle": str(bundle),
            "user_sessions_touched": False,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("launch")
    for name in ("doctor", "cleanup", "negative-control"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
    p = sub.add_parser("drive")
    p.add_argument("--run", required=True)
    p.add_argument(
        "--feature",
        choices=("screens", "world", "live", "interfaces"),
        default="screens",
    )
    args = parser.parse_args()
    if args.action == "launch":
        BASE.mkdir(parents=True, exist_ok=True)
        run = BASE / str(uuid.uuid4())
        run.mkdir(mode=0o700)
        write(
            run / "run.json",
            {
                "owner": "chromatic-project-verify",
                "repo": str(ROOT),
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "cleaned_up": False,
            },
        )
        execute(
            run,
            "build",
            [
                PYTHON,
                "-m",
                "chromatic_demo.playground",
                "--repo",
                ROOT,
                "--content",
                ROOT / "chromatic_demo/worlds/last_ascent.json",
                "--output",
                run / "rom",
            ],
        )
        print("RUN=" + str(run))
        return
    run, record = run_path(args.run)
    if args.action == "doctor":
        doctor(run)
    elif args.action == "drive":
        doctor(run)
        if args.feature == "screens":
            execute(
                run,
                "screens",
                [
                    PYTHON,
                    ROOT / "tests/chromatic_demo/verify_screen_frames.py",
                    run / "rom",
                    "--output-dir",
                    run / "screens",
                ],
            )
            report = json.loads((run / "screens/coverage.json").read_text())
            if (
                report["status"] != "passed"
                or report["coverage_enforced"] is not True
            ):
                raise AssertionError(
                    "Screen gate did not enforce complete coverage"
                )
            for name in ("phases", "methods", "areas"):
                if set(report["required_" + name]) != set(
                    report["observed_" + name]
                ):
                    raise AssertionError(
                        "Missing required screen coverage: " + name
                    )
            if report["missing_paths"] or report["checked_frame_count"] <= 0:
                raise AssertionError(
                    "Screen gate omitted required paths or frame checks"
                )
        elif args.feature == "interfaces":
            execute(
                run,
                "interfaces",
                [
                    PICKER_PYTHON,
                    ROOT / "tests/chromatic_demo/verify_interface_flows.py",
                    run / "rom",
                    "--output-dir",
                    run / "interfaces",
                    "--picker-model",
                    ROOT / "venv/chromatic-picker-model",
                ],
            )
            report = json.loads((run / "interfaces/coverage.json").read_text())
            flows = report["interface_flows"]
            if report["status"] != "passed" or {
                flow["method_id"] for flow in flows
            } != set(report["required_methods"]):
                raise AssertionError("Incomplete conversation interface flows")
            if any(
                flow["explicit_send_count"] != 1
                or flow["quest_flags_after"] != 32
                or flow["inventory_after"] != 3
                for flow in flows
            ):
                raise AssertionError(
                    "Conversation confirmation effects were not verified"
                )
        elif args.feature == "world":
            for label, script in [
                ("movement", "verify_movement_frames.py"),
                ("world", "verify_playground.py"),
                ("layout", "verify_playground_build.py"),
            ]:
                execute(
                    run,
                    label,
                    [
                        PYTHON,
                        ROOT / "tests/chromatic_demo" / script,
                        run / "rom",
                    ],
                )
        else:
            execute(
                run,
                "live",
                [
                    PICKER_PYTHON,
                    ROOT / "tests/chromatic_demo/verify_live_bridge.py",
                    "--build",
                    run / "rom",
                    "--output-dir",
                    run / "live",
                ],
            )
    elif args.action == "negative-control":
        old = ROOT / "build/chromatic/playground-before-ui-fix"
        digest = hashlib.sha256(
            (old / "playground.gbc").read_bytes()
        ).hexdigest()
        if (
            digest
            != "b9b54bf6d16cfbaf562b8ed1d0f65a085d7e22e7788697c844d0d6005df6bc93"
        ):
            raise ValueError(
                "Historical control is absent or has a different digest; do not fabricate it"
            )
        command = [
            str(PYTHON),
            str(ROOT / "tests/chromatic_demo/verify_screen_frames.py"),
            str(old),
            "--smoke",
            "--output-dir",
            str(run / "negative-control"),
        ]
        result = execute(
            run, "negative-control", command, timeout=120, allow_failure=True
        )
        text = result.stdout + result.stderr
        detected = result.returncode == 1 and (
            "all-white LCD frame" in text
            or "all-white frame" in text
            or "stable header was erased" in text
        )
        write(
            run / "negative-control.json",
            {
                "command": command,
                "rom_sha256": digest,
                "exit_code": result.returncode,
                "known_blink_detected": detected,
            },
        )
        if not detected:
            raise AssertionError(
                "Negative control did not detect the actual rendering defect"
            )
        print("Known blinking build rejected; failure evidence retained.")
    else:
        files = sorted(
            str(p.relative_to(run)) for p in run.rglob("*") if p.is_file()
        )
        record["cleaned_up"] = True
        record["cleanup"] = (
            "Owned short-lived child commands have exited. Harnesses close their own runtimes. No user GUI, browser, or physical device instance was driven."
        )
        record["retained_evidence_files"] = len(files)
        write(run / "run.json", record)
        write(
            run / "cleanup.json",
            {"retained_files": files, "evidence_removed": False},
        )
        assert all((run / name).exists() for name in files)
        print(
            f"Cleanup complete; {len(files)} evidence files retained at {run}"
        )


if __name__ == "__main__":
    main()
