"""Drive the real CLI and Mac game inputs through an existing Ollama model."""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pygame

import run_tuxemon

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "tests/custom_game")
)
import test_game

destination = Path(
    os.environ.get("TUXEMON_LIVE_EVIDENCE", "work/live-evidence")
)
destination.mkdir(parents=True, exist_ok=True)
test_game.EVIDENCE = destination
receipt = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "inference": "actual Ollama, no synthetic server or response substitution",
    "model": os.environ["TUXEMON_OLLAMA_MODEL"],
    "endpoint": os.environ["TUXEMON_OLLAMA_URL"],
    "actions": [],
    "turns": [],
}
original_display = run_tuxemon.init_display


def record(driver, name):
    driver.capture(name)
    receipt["actions"].append(
        {
            "name": name,
            "phase": driver.model.phase,
            "draft": driver.model.draft,
            "keyboard": driver.model.keyboard,
            "frame": driver.client.frame_number,
        }
    )


def send(driver):
    model = driver.model
    driver.choose("PREVIEW")
    exact = model.draft
    record(driver, f"{len(receipt['turns'])}-preview")
    assert model.pending is None
    before = (model.flags, model.inventory)
    driver.key(pygame.K_RETURN)
    deadline = time.monotonic() + 125
    frames = driver.client.frame_number
    while model.phase == "waiting" and time.monotonic() < deadline:
        driver.tick()
        time.sleep(0.01)
    receipt["last_message"] = model.message
    assert model.phase == "npc_reply", model.message
    assert model.message.strip() != exact.strip(), "NPC echoed player verbatim"
    assert (model.flags, model.inventory) == before
    assert driver.client.frame_number > frames
    receipt["turns"].append({"player": exact, "npc": model.message})
    record(driver, f"{len(receipt['turns'])}-live-reply")


def finite_loop(client):
    from tuxemon.session import local_session

    driver = test_game.Driver(client)
    try:
        driver.tick(100)
        receipt["video_driver"] = pygame.display.get_driver()
        receipt["pygame"] = pygame.version.ver
        receipt["spawn"] = list(local_session.player.tile_pos)
        assert receipt["spawn"] == [4, 7]
        record(driver, "01-map-spawn")
        assert driver.walk(pygame.K_UP, 2) == (4, 5)
        record(driver, "02-walk-to-professor")
        driver.key(pygame.K_RETURN)
        assert client.current_state.name == "CustomConversationState"
        assert driver.model.scene["name"] == "Professor"
        driver.key(pygame.K_RETURN)
        assert driver.model.draft == "ask"
        assert not driver.model.keyboard
        record(driver, "03-constrained-chip")
        driver.type(" Professor, my name is Cedar. Who are you?")
        assert (
            driver.model.draft
            == "ask Professor, my name is Cedar. Who are you?"
        )
        record(driver, "04-keyboard-switch")
        driver.key(pygame.K_TAB)
        assert not driver.model.keyboard
        send(driver)
        assert "professor" in driver.model.message.lower(), (
            driver.model.message
        )
        driver.choose("Continue conversation")
        driver.type("What name did I tell you? Reply with that name.")
        driver.key(pygame.K_TAB)
        send(driver)
        assert "cedar" in driver.model.message.lower(), driver.model.message
        assert len(driver.model.conversations[0]) == 2
        receipt["result"] = "PASS"
    except BaseException as error:
        receipt["result"] = "FAIL"
        receipt["error"] = repr(error)
        driver.capture("failure")
        raise
    finally:
        receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
        (destination / "result.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )
        client.network_manager.shutdown()
        pygame.quit()
    print(json.dumps(receipt, indent=2))


def display(mode):
    context = original_display(mode)
    from tuxemon.client import LocalPygameClient
    from tuxemon.network.manager import NetworkManager

    NetworkManager.initialize = lambda self: None
    LocalPygameClient.main = finite_loop
    return context


run_tuxemon.init_display = display
run_tuxemon.launch_game(["--custom-game"])

if receipt.get("result") != "PASS":
    raise SystemExit(1)
