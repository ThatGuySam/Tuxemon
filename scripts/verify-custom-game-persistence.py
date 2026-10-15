"""Verify persistence across separate native or SDL game processes."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pygame

import run_tuxemon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/custom_game"))
import test_game

PROFESSOR_DRAFT = "Lumi, not Luma; 2 Vorpax"
QUARTERMASTER_DRAFT = "Keep my crystal."


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--stage",
        choices=[
            "seed",
            "resume",
            "recheck",
            "other",
            "broken",
            "future",
            "reset",
            "pending",
            "pending-resume",
        ],
    )
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def run_stage(args):
    destination = args.output / args.stage
    destination.mkdir(parents=True, exist_ok=True)
    test_game.EVIDENCE = destination
    receipt = {
        "stage": args.stage,
        "pid": os.getpid(),
        "profile": os.environ["TUXEMON_CUSTOM_PROFILE"],
        "result": "FAIL",
        "inference": (
            "actual Ollama"
            if args.stage in ("seed", "resume")
            else "synthetic pending-request fixture"
            if args.stage == "pending"
            else "none"
        ),
        "actions": [],
    }
    original_display = run_tuxemon.init_display
    from tuxemon.custom_game.runtime import Ollama

    original_reply = Ollama.reply

    def record_reply(provider, npc, token):
        text = original_reply(provider, npc, token)
        receipt.setdefault("provider_replies", []).append(text)
        return text

    Ollama.reply = record_reply

    def capture(driver, name):
        driver.capture(name)
        receipt["actions"].append(
            {
                "name": name,
                "draft": driver.model.draft,
                "npc": driver.model.scene["id"],
                "method": driver.model.method,
                "phase": driver.model.phase,
            }
        )

    def quartermaster(driver):
        driver.key(pygame.K_F1)
        driver.choose("Return to map")
        assert driver.walk(pygame.K_RIGHT, 4) == (8, 5)
        driver.key(pygame.K_UP)
        driver.key(pygame.K_RETURN)
        assert driver.model.scene["id"] == "quartermaster"

    def send(driver):
        driver.choose("PREVIEW")
        capture(driver, "exact-preview")
        before = (driver.model.flags, driver.model.inventory)
        driver.key(pygame.K_RETURN)
        deadline = time.monotonic() + 125
        while driver.model.phase == "waiting" and time.monotonic() < deadline:
            driver.tick()
            time.sleep(0.01)
        assert driver.model.phase == "npc_reply", driver.model.message
        assert before == (driver.model.flags, driver.model.inventory)
        receipt["reply"] = driver.model.message
        capture(driver, "reply")

    def finite_loop(client):
        driver = test_game.Driver(client)
        server = None
        try:
            driver.tick(100)
            model = driver.model
            receipt["video_driver"] = pygame.display.get_driver()
            receipt["save_path"] = str(model.store.path)
            receipt["notice"] = model.store.notice
            assert (
                model.worker is None
                and model.pending is None
                and model.request is None
            )
            assert driver.walk(pygame.K_UP, 2) == (4, 5)
            driver.key(pygame.K_RETURN)
            assert model.scene["id"] == "professor"
            capture(driver, "opened-professor")
            if args.stage == "seed":
                assert not model.draft and not model.conversations
                driver.key(pygame.K_RETURN)
                assert model.draft == "ask"
                driver.type(
                    " Professor, my name is Cedar. Who are you? Reply in one short ASCII sentence."
                )
                driver.key(pygame.K_TAB)
                send(driver)
                assert "professor" in model.message.lower(), model.message
                assert len(model.conversations[0]) == 1
                driver.choose("Continue conversation")
                driver.method("Grouped alphabet")
                driver.type(PROFESSOR_DRAFT)
                driver.key(pygame.K_TAB)
                capture(driver, "unfinished-professor")
                quartermaster(driver)
                assert not model.draft and not model.conversations.get(1)
                assert "Cedar" not in model.dialogue_context()
                driver.method("Radial groups")
                driver.type(QUARTERMASTER_DRAFT)
                driver.key(pygame.K_TAB)
                capture(driver, "unfinished-quartermaster")
            elif args.stage in ("resume", "recheck"):
                assert model.draft == PROFESSOR_DRAFT and model.method == 4
                assert "Cedar" in model.conversations[0][0][0]
                assert QUARTERMASTER_DRAFT not in model.dialogue_context()
                assert model.pending is None and model.worker is None
                capture(driver, "restored-professor")
                if args.stage == "resume":
                    driver.clear()
                    driver.type(
                        "What name did I tell you? Reply with that name."
                    )
                    driver.key(pygame.K_TAB)
                    send(driver)
                    assert "cedar" in model.message.lower(), model.message
                    driver.choose("Continue conversation")
                    driver.type(PROFESSOR_DRAFT)
                    driver.key(pygame.K_TAB)
                quartermaster(driver)
                assert model.draft == QUARTERMASTER_DRAFT and model.method == 7
                assert not model.conversations.get(1)
                assert "Cedar" not in model.dialogue_context()
                capture(driver, "restored-quartermaster")
            elif args.stage == "other":
                assert not model.draft and not model.conversations
                driver.method("Predictive grid")
                driver.type("I am Lumi, not Cedar.")
                driver.key(pygame.K_TAB)
                capture(driver, "separate-profile")
            elif args.stage in ("broken", "future"):
                assert not model.store.writable
                assert not model.conversations and not model.draft
                assert "retained" in model.store.notice
                driver.type("Temporary only")
                capture(driver, "save-disabled-visible")
                driver.key(pygame.K_F1)
                driver.choose("Reset story")
                driver.choose("Reset story, draft and all NPC conversations")
                assert "Saved file retained" in model.message
                capture(driver, "reset-retains-damaged-file")
            elif args.stage == "reset":
                assert (
                    model.draft == "I am Lumi, not Cedar."
                    and model.method == 3
                )
                driver.key(pygame.K_F1)
                driver.choose("Reset story")
                driver.choose("Reset story, draft and all NPC conversations")
                assert not model.conversations and not any(
                    model.npc_drafts.values()
                )
                capture(driver, "cleared-profile")
            elif args.stage == "pending":
                test_game.SyntheticOllama.mode = "delayed"
                test_game.SyntheticOllama.gate.clear()
                server = ThreadingHTTPServer(
                    ("127.0.0.1", 0), test_game.SyntheticOllama
                )
                threading.Thread(
                    target=server.serve_forever, daemon=True
                ).start()
                model.endpoint = f"http://127.0.0.1:{server.server_port}"
                model.model = "SYNTHETIC pending request fixture"
                driver.type("Do not resend this.")
                driver.key(pygame.K_TAB)
                driver.choose("PREVIEW")
                driver.key(pygame.K_RETURN)
                assert model.pending is not None and model.phase == "waiting"
                receipt["pending_at_quit"] = True
                capture(driver, "quit-with-pending-request")
            elif args.stage == "pending-resume":
                assert model.draft == "Do not resend this."
                assert not model.conversations
                assert (
                    model.pending is None
                    and model.worker is None
                    and model.request is None
                )
                driver.tick(60)
                assert model.worker is None and model.phase == "editor"
                capture(driver, "pending-not-replayed")
            receipt["result"] = "PASS"
            receipt["histories"] = {
                model.world["npcs"][index]["id"]: turns
                for index, turns in model.conversations.items()
            }
            receipt["notice"] = model.store.notice
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            receipt["quit_event_posted"] = True
            driver.tick()
        except Exception as error:
            receipt["error"] = repr(error)
            capture(driver, "failure")
            raise
        finally:
            receipt["recorded_at"] = datetime.now(timezone.utc).isoformat()
            (destination / "result.json").write_text(
                json.dumps(receipt, indent=2) + "\n"
            )
            client.network_manager.shutdown()
            if server is not None:
                test_game.SyntheticOllama.gate.set()
                server.shutdown()
                server.server_close()

    def display(mode):
        context = original_display(mode)
        from tuxemon.client import LocalPygameClient
        from tuxemon.network.manager import NetworkManager

        NetworkManager.initialize = lambda self: None
        LocalPygameClient.main = finite_loop
        return context

    run_tuxemon.init_display = display
    run_tuxemon.launch_game(["--custom-game"])
    if receipt["result"] != "PASS":
        raise SystemExit(1)


def run_journey(args):
    args.output = args.output.resolve()
    if args.output.exists():
        raise SystemExit(
            "Choose a new evidence directory; existing evidence is preserved."
        )
    args.output.mkdir(parents=True)
    if not args.live:
        raise SystemExit(
            "This journey requires --live and an explicitly configured existing Ollama model."
        )
    if not os.environ.get("TUXEMON_OLLAMA_MODEL") or not os.environ.get(
        "TUXEMON_OLLAMA_URL"
    ):
        raise SystemExit("Set TUXEMON_OLLAMA_MODEL and TUXEMON_OLLAMA_URL.")
    userdata = args.output / "userdata"
    save_dir = userdata / "saves/custom-last-ascent"
    steps = [
        ("seed", "cedar"),
        ("resume", "cedar"),
        ("other", "lumi"),
        ("recheck", "cedar"),
        ("broken", "broken"),
        ("future", "future"),
        ("reset", "lumi"),
        ("pending", "pending"),
        ("pending-resume", "pending"),
    ]
    receipts = []
    preserved = {}
    for stage, profile in steps:
        if stage in ("broken", "future"):
            if stage == "broken":
                raw = b'{"schema": "tuxemon.custom-conversations", "version":'
            else:
                data = json.loads((save_dir / "cedar.json").read_text())
                data["version"] = 999
                data["profile"] = "future"
                raw = json.dumps(data).encode()
            (save_dir / f"{profile}.json").write_bytes(raw)
            preserved[profile] = raw
        cedar_before = (
            (save_dir / "cedar.json").read_bytes()
            if (save_dir / "cedar.json").exists()
            else None
        )
        command = [
            sys.executable,
            str(ROOT / "scripts/cloud_game.py"),
            "scripts/verify-custom-game-persistence.py",
            "--stage",
            stage,
            "--output",
            str(args.output),
            "--live",
        ]
        env = {
            **os.environ,
            "TUXEMON_USERDATA": str(userdata),
            "TUXEMON_CUSTOM_PROFILE": profile,
        }
        with (args.output / f"{stage}.log").open("w") as log:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
        receipt = json.loads((args.output / stage / "result.json").read_text())
        assert result.returncode == 0 and receipt["result"] == "PASS", (
            stage,
            receipt,
        )
        receipts.append(receipt)
        if stage in (
            "other",
            "reset",
            "broken",
            "future",
            "pending",
            "pending-resume",
        ):
            assert (save_dir / "cedar.json").read_bytes() == cedar_before
        if profile in preserved:
            assert (save_dir / f"{profile}.json").read_bytes() == preserved[
                profile
            ]
    reset = json.loads((save_dir / "lumi.json").read_text())
    assert all(
        not npc["draft"] and not npc["history"]
        for npc in reset["npcs"].values()
    )
    assert len({r["pid"] for r in receipts}) == len(receipts)
    result = {
        "result": "PASS",
        "stages": receipts,
        "distinct_processes": len(receipts),
        "damaged_files_preserved": {
            key: hashlib.sha256(raw).hexdigest()
            for key, raw in preserved.items()
        },
        "inference": "two real Ollama calls, plus one labeled synthetic pending-request fixture",
    }
    (args.output / "result.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "result": "PASS",
                "processes": len(receipts),
                "evidence": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    args = arguments()
    if args.stage:
        run_stage(args)
    else:
        run_journey(args)
