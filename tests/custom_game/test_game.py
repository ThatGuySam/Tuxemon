"""Actual engine input/render evidence. HTTP fixture is SYNTHETIC, not Ollama."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pygame
import pytest

EVIDENCE = Path("work/custom-game-evidence")


class SyntheticOllama(BaseHTTPRequestHandler):
    requests = []
    mode = "success"
    gate = threading.Event()

    def do_POST(self):
        assert self.path == "/api/chat"
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(body)
        mode = self.mode
        if mode == "delayed":
            self.gate.wait(3)
        if mode == "http_error":
            self.send_error(503, "SYNTHETIC service unavailable")
            return
        payload = {
            "done": True,
            "message": {
                "content": (
                    "SYNTHETIC HTTP FIXTURE, not live inference. I am the camp NPC. "
                    "I remember your question, but no quest action has happened. "
                    + "Please review the separate quest action carefully. "
                    * 55
                )
            },
        }
        if mode == "malformed":
            payload = {"done": False}
        raw = json.dumps(payload).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except BrokenPipeError:
            pass

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def game():
    from tuxemon.prepare import pygame_init

    context = pygame_init()
    # Import after display setup, as the real launcher does.
    from tuxemon.client import LocalPygameClient
    from tuxemon.custom_game.runtime import launch
    from tuxemon.network.manager import NetworkManager
    from tuxemon.session import local_session
    from tuxemon.user_config import CONFIG

    # Multiplayer is unrelated to this single-player scenario. Avoid port 40081
    # collisions with the independent cloud verification checkout.
    original = NetworkManager.initialize
    NetworkManager.initialize = lambda self: None
    try:
        client = LocalPygameClient.create(CONFIG.copy(), context)
    finally:
        NetworkManager.initialize = original
    local_session.set_client(client)
    launch(client)
    driver = Driver(client)
    driver.tick(100)
    yield driver
    client.network_manager.shutdown()
    pygame.quit()


class Driver:
    def __init__(self, client):
        self.client = client
        self.use_a = False
        EVIDENCE.mkdir(parents=True, exist_ok=True)

    @property
    def model(self):
        return self.client.custom_scenario

    def tick(self, frames=1):
        for _ in range(frames):
            self.client.update(1 / 60)
            self.client.draw()
            pygame.display.update()

    def key(self, key, frames=1, text=""):
        if key == pygame.K_RETURN and self.use_a:
            from tuxemon.platform.const import buttons
            from tuxemon.platform.events import PlayerInput

            list(
                self.client.event_manager.process_events(
                    [PlayerInput(buttons.A, 1, 1)]
                )
            )
            self.tick(3)
            return
        pygame.event.post(
            pygame.event.Event(pygame.KEYDOWN, key=key, unicode=text)
        )
        self.tick(frames)
        pygame.event.post(
            pygame.event.Event(pygame.KEYUP, key=key, unicode=text)
        )
        self.tick(2)

    def choose(self, label):
        if (
            self.model.phase == "editor"
            and self.model.method in (5, 7)
            and self.model.cursor == 0
            and label in ("PREVIEW", "QUEST ACTIONS")
        ):
            self.key(pygame.K_ESCAPE)
        assert label in self.model.options(), (
            label,
            self.model.phase,
            self.model.options(),
        )
        for _ in range(len(self.model.options())):
            if self.model.options()[self.model.cursor] == label:
                self.key(pygame.K_RETURN)
                return
            self.key(pygame.K_RIGHT)
        pytest.fail("Option unreachable with advertised keys")

    def type(self, text):
        if not self.model.keyboard:
            self.key(pygame.K_TAB)
        for char in text:
            if char.isupper():
                pygame.event.post(
                    pygame.event.Event(
                        pygame.KEYDOWN, key=pygame.K_LSHIFT, unicode=""
                    )
                )
                self.tick()
            self.key(ord(char.lower()), text=char)
            if char.isupper():
                pygame.event.post(
                    pygame.event.Event(
                        pygame.KEYUP, key=pygame.K_LSHIFT, unicode=""
                    )
                )
                self.tick()
                assert self.model.phase == "editor", (
                    "Shift must type capitals in keyboard mode"
                )

    def clear(self):
        for _ in range(len(self.model.draft)):
            self.key(pygame.K_BACKSPACE)

    def method(self, name):
        self.key(pygame.K_F1)
        self.choose("Input methods")
        self.choose(name)
        assert self.model.phase == "editor"

    def capture(self, name):
        self.tick()
        raw = pygame.image.tobytes(self.client.screen, "RGB")
        assert len(set(raw)) > 20
        pygame.image.save(self.client.screen, EVIDENCE / (name + ".png"))

    def wait_reply(self, phase="npc_reply"):
        deadline = time.monotonic() + 5
        while self.model.phase == "waiting" and time.monotonic() < deadline:
            self.tick()
            time.sleep(0.005)
        assert self.model.phase == phase, self.model.message

    def walk(self, direction, steps):
        from tuxemon.session import local_session

        start = local_session.player.tile_pos
        # Measured engine walk rate is 3.75 tiles/sec. Stop by tile transition,
        # rather than teleporting or mutating entity position.
        pygame.event.post(
            pygame.event.Event(pygame.KEYDOWN, key=direction, unicode="")
        )
        for _ in range(steps * 24 + 20):
            self.tick()
            now = local_session.player.tile_pos
            if abs(now[0] - start[0]) + abs(now[1] - start[1]) >= steps:
                break
        pygame.event.post(
            pygame.event.Event(pygame.KEYUP, key=direction, unicode="")
        )
        self.tick(20)
        return local_session.player.tile_pos


def check_movement_npc_and_all_nine_editors(game):
    from tuxemon.custom_game.composer import METHODS
    from tuxemon.platform.const import buttons
    from tuxemon.platform.events import PlayerInput
    from tuxemon.session import local_session

    assert game.client.get_map_name() == "custom_last_ascent.tmx"
    assert local_session.player.tile_pos == (4, 7)
    assert all(game.client.get_npc(f"custom_ascent_{i}") for i in range(5))
    game.capture("01-map-spawn")
    assert game.walk(pygame.K_UP, 2) == (4, 5)
    game.capture("02-walk-to-professor")
    game.key(pygame.K_RETURN)
    assert game.client.current_state.name == "CustomConversationState"
    assert game.model.scene["name"] == "Professor"
    game.capture("03-return-opens-npc")
    start = local_session.player.tile_pos
    game.key(pygame.K_RETURN)
    assert game.model.draft == "ask"
    game.clear()
    # A uses the same activation handler as actual Return.
    # process_events is a generator; materialize it through the public engine.
    list(
        game.client.event_manager.process_events(
            [PlayerInput(buttons.A, 1, 1)]
        )
    )
    assert game.model.draft == "ask"
    game.clear()
    for activation in ("Return", "A"):
        game.use_a = activation == "A"
        for method, name in METHODS:
            game.method(name)
            assert game.model.method == method
            if method == 1:
                game.key(pygame.K_RETURN)
            elif method == 0:
                for _ in range(3):
                    game.key(pygame.K_RETURN)
            elif method == 2:
                game.type("hsipmerftct")
                game.key(pygame.K_TAB)
                game.key(pygame.K_RETURN)
                assert (
                    game.model.draft
                    == game.model.scene["replies"][0]["utterance"]
                )
            elif method == 3:
                game.key(pygame.K_RETURN)
                game.choose("COMPLETE")
                assert game.model.draft == "ask"
            elif method == 4:
                game.key(pygame.K_RETURN)
                game.key(pygame.K_RETURN)
            elif method == 5:
                game.key(pygame.K_UP)
                game.key(pygame.K_RETURN)
            elif method == 6:
                game.key(pygame.K_RETURN)
                game.key(pygame.K_DOWN)
                for _ in range(4):
                    if game.model.draft:
                        break
                    game.key(pygame.K_RETURN)
            elif method == 7:
                game.key(pygame.K_RIGHT)
                game.key(pygame.K_RETURN)
                game.key(pygame.K_RETURN)
                assert game.model.draft == "h"
            else:
                game.key(pygame.K_RETURN)
                game.type("Lumi not Luma; 2 Vorpax")
            assert game.model.draft, (name, game.model.message)
            game.capture(
                f"editor-{activation}-{method}-{name.replace(' / ', '-').replace(' ', '-')}"
            )
            game.choose("PREVIEW")
            assert game.model.phase == "preview"
            draft = game.model.draft
            game.capture(f"preview-{activation}-{method}")
            game.choose("Back to editing")
            assert game.model.draft == draft
            game.clear()
    game.use_a = False
    assert local_session.player.tile_pos == start, (
        "Editor controls must never move player"
    )


def check_http_followup_cancellation_errors_and_drafts(game):
    SyntheticOllama.requests.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), SyntheticOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    model = game.model
    model.endpoint = f"http://127.0.0.1:{server.server_port}"
    model.model = "synthetic-fixture-not-a-real-model"
    game.method("Host / keyboard")
    game.clear()
    exact = "Lumi, not Luma. I refuse 2 packs; Vorpax?"
    game.type(exact)
    game.choose("PREVIEW")
    assert not SyntheticOllama.requests
    game.capture("04-exact-preview-no-request")
    flags_items = (model.flags, model.inventory)
    game.key(pygame.K_RETURN)
    game.wait_reply()
    assert SyntheticOllama.requests[0]["messages"][-1]["content"] == exact
    system = SyntheticOllama.requests[0]["messages"][0]["content"]
    assert (
        "You are Professor" in system and "Do not repeat or rewrite" in system
    )
    assert "SYNTHETIC HTTP FIXTURE" in model.message
    assert (model.flags, model.inventory) == flags_items
    game.capture("05-synthetic-http-npc-reply")
    assert model.reply_pages > 1
    game.key(pygame.K_RIGHT)
    assert model.reply_page == 1
    game.capture("06-reply-next-page")
    game.choose("Continue conversation")
    game.type("Who are you?")
    game.choose("PREVIEW")
    game.key(pygame.K_RETURN)
    game.wait_reply()
    assert (
        "Lumi, not Luma"
        in SyntheticOllama.requests[-1]["messages"][0]["content"]
    )
    assert (
        "SYNTHETIC HTTP FIXTURE"
        in SyntheticOllama.requests[-1]["messages"][0]["content"]
    )
    assert len(model.conversations[0]) == 2
    game.capture("07-followup-synthetic")
    game.choose("Continue conversation")
    for mode in ("http_error", "malformed"):
        SyntheticOllama.mode = mode
        game.clear()
        game.type("Do not spend my crystal.")
        draft = model.draft
        game.choose("PREVIEW")
        game.key(pygame.K_RETURN)
        game.wait_reply("editor")
        assert model.draft == draft and len(model.conversations[0]) == 2
        assert "Draft retained" in model.message
        game.capture("error-" + mode)
    SyntheticOllama.mode = "delayed"
    SyntheticOllama.gate.clear()
    game.choose("PREVIEW")
    game.key(pygame.K_RETURN)
    game.tick(5)
    assert model.phase == "waiting"
    frames = game.client.frame_number
    game.tick(30)
    assert game.client.frame_number == frames + 30
    game.key(pygame.K_ESCAPE)
    assert model.phase == "editor" and model.pending is None
    assert model.draft == draft
    # Closing and reopening cannot bypass the single-worker bound or lose a draft.
    game.key(pygame.K_F1)
    game.choose("Return to map")
    game.key(pygame.K_RETURN)
    assert model.draft == draft and model.worker.is_alive()
    game.type("?")
    draft = model.draft
    SyntheticOllama.gate.set()
    for _ in range(50):
        game.tick()
        time.sleep(0.005)
    assert len(model.conversations[0]) == 2 and model.draft == draft
    game.capture("08-cancel-retains-draft")
    # Exercise a real socket timeout in the actual game's worker, with a short
    # deterministic deadline. The production default remains 15 seconds.
    import tuxemon.states.custom_conversation as overlay

    real_adapter = overlay.Ollama
    overlay.Ollama = lambda endpoint, name: real_adapter(
        endpoint, name, timeout=0.05
    )
    SyntheticOllama.gate.clear()
    try:
        game.choose("PREVIEW")
        game.key(pygame.K_RETURN)
        game.wait_reply("editor")
        assert model.draft == draft and len(model.conversations[0]) == 2
        assert "Draft retained" in model.message
        game.capture("error-socket-timeout")
    finally:
        overlay.Ollama = real_adapter
        SyntheticOllama.gate.set()
    SyntheticOllama.mode = "success"
    server.shutdown()
    server.server_close()


def check_real_npc_memory_and_guarded_engine_items(game):
    from tuxemon.session import local_session

    model = game.model
    professor_draft = model.draft
    game.key(pygame.K_F1)
    game.choose("Return to map")
    assert game.client.current_state.name == "WorldState"
    assert game.walk(pygame.K_RIGHT, 4) == (8, 5)
    game.key(pygame.K_UP)  # Face real blocking Quartermaster.
    game.key(pygame.K_RETURN)
    assert model.npc == 1 and model.draft == ""
    assert not model.conversations.get(1)
    game.type("I need two packs, not one.")
    game.choose("QUEST ACTIONS")
    game.choose("Request two packs")
    game.capture("09-quest-separate-confirmation")
    assert local_session.player.bag.find_item("custom_crystal")
    game.choose("Confirm separate scripted quest action")
    assert not local_session.player.bag.find_item("custom_supply_pack")
    assert local_session.player.bag.find_item("custom_crystal")
    game.key(pygame.K_RETURN)
    game.choose("QUEST ACTIONS")
    game.choose("Trade for one pack")
    assert local_session.player.bag.find_item("custom_crystal")
    game.choose("Confirm separate scripted quest action")
    assert not local_session.player.bag.find_item("custom_crystal")
    assert (
        local_session.player.bag.find_item("custom_supply_pack").quantity == 1
    )
    game.capture("10-guarded-real-bag-trade")
    game.key(pygame.K_RETURN)
    game.choose("QUEST ACTIONS")
    game.choose("Trade for one pack")
    game.choose("Confirm separate scripted quest action")
    assert "guard refused" in model.message
    assert (
        local_session.player.bag.find_item("custom_supply_pack").quantity == 1
    )
    game.capture("11-repeat-trade-refused")
    game.key(pygame.K_F1)
    game.choose("Return to map")
    assert game.walk(pygame.K_LEFT, 4) == (4, 5)
    game.key(pygame.K_UP)
    game.key(pygame.K_RETURN)
    assert model.npc == 0 and model.draft == professor_draft
    assert len(model.conversations[0]) == 2
    game.key(pygame.K_F1)
    game.choose("Reset story")
    game.choose("Reset story, draft and all NPC conversations")
    assert model.flags == 0 and model.inventory == 3
    assert not model.conversations and not model.npc_drafts and not model.draft
    game.capture("12-repeatable-reset")


def check_tracker_medic_warden(game):
    from tuxemon.session import local_session

    game.key(pygame.K_F1)
    game.choose("Return to map")
    assert game.walk(pygame.K_RIGHT, 8) == (12, 5)
    game.key(pygame.K_UP)
    game.key(pygame.K_RETURN)
    assert game.model.scene["name"] == "Tracker Iona"
    game.choose("QUEST ACTIONS")
    game.choose("Correct tag name")
    game.choose("Confirm separate scripted quest action")
    assert game.model.flags == 2
    game.key(pygame.K_RETURN)
    game.choose("QUEST ACTIONS")
    game.choose("Confirm dry trail")
    game.choose("Confirm separate scripted quest action")
    assert game.model.flags == 6
    game.capture("13-tracker-name-and-safe-route")
    game.key(pygame.K_F1)
    game.choose("Return to map")
    assert game.walk(pygame.K_DOWN, 5) == (12, 10)
    assert game.walk(pygame.K_RIGHT, 2) == (14, 10)
    game.key(pygame.K_UP)
    game.key(pygame.K_RETURN)
    assert game.model.scene["name"] == "Warden Vale"
    game.choose("QUEST ACTIONS")
    game.choose("Refuse shortcut")
    game.choose("Confirm separate scripted quest action")
    assert game.model.flags == 6
    assert not local_session.player.bag.find_item("custom_permit")
    game.key(pygame.K_RETURN)
    game.choose("QUEST ACTIONS")
    game.choose("Ask for permit")
    assert not local_session.player.bag.find_item("custom_permit")
    game.choose("Confirm separate scripted quest action")
    assert local_session.player.bag.find_item("custom_permit").quantity == 1
    game.capture("14-warden-refusal-and-guarded-permit")
    game.key(pygame.K_F1)
    game.choose("Return to map")
    assert game.walk(pygame.K_LEFT, 8) == (6, 10)
    game.key(pygame.K_UP)
    game.key(pygame.K_RETURN)
    assert game.model.scene["name"] == "Medic Ren"
    game.choose("QUEST ACTIONS")
    game.choose("Refuse kit use")
    game.choose("Confirm separate scripted quest action")
    assert local_session.player.bag.find_item("custom_aid_kit")
    game.key(pygame.K_RETURN)
    game.choose("QUEST ACTIONS")
    game.choose("Use kit and escort")
    assert local_session.player.bag.find_item("custom_aid_kit")
    game.choose("Confirm separate scripted quest action")
    assert not local_session.player.bag.find_item("custom_aid_kit")
    assert game.model.flags & 65 == 65
    game.capture("15-medic-competing-needs-and-kit")
    flags_items = (game.model.flags, game.model.inventory)
    game.key(pygame.K_F1)
    game.choose("Return to map")
    # Reconstruct scenario runtime through a real map interaction. Existing
    # engine flags/items must survive, as they would after a restored save.
    del game.client.custom_scenario
    game.key(pygame.K_RETURN)
    assert (game.model.flags, game.model.inventory) == flags_items
    game.capture("16-engine-state-reconstruction")


def test_actual_game_acceptance(game):
    """A single complete player journey, without inter-test state dependencies."""
    check_movement_npc_and_all_nine_editors(game)
    check_http_followup_cancellation_errors_and_drafts(game)
    check_real_npc_memory_and_guarded_engine_items(game)
    check_tracker_medic_warden(game)


@pytest.mark.parametrize(
    "endpoint, model",
    [
        ("", "model"),
        ("file:///tmp/model", "model"),
        ("http://user:password@example.com", "model"),
        ("https://example.com/api/chat", "model"),
        ("https://example.com", ""),
    ],
)
def test_ollama_requires_explicit_origin_and_model(endpoint, model):
    from tuxemon.custom_game.runtime import Ollama

    with pytest.raises(ValueError):
        Ollama(endpoint, model)


def test_translation_recompile_refreshes_existing_gettext_cache(tmp_path):
    """New scenario item names must not break an existing cached campaign."""
    from gettext import translation

    from tuxemon.locale.compiler import GettextCompiler

    source = tmp_path / "base.po"
    output = tmp_path / "l18n/en_US/LC_MESSAGES/base.mo"
    compiler = GettextCompiler(tmp_path)
    source.write_text('msgid "existing_item"\nmsgstr "Existing item"\n')
    compiler.compile_gettext(source, output)
    first = translation("base", tmp_path / "l18n", ["en_US"])
    assert first.gettext("custom_crystal") == "custom_crystal"
    source.write_text(
        'msgid "existing_item"\nmsgstr "Existing item"\n\nmsgid "custom_crystal"\nmsgstr "Expedition crystal"\n'
    )
    compiler.compile_gettext(source, output)
    refreshed = translation("base", tmp_path / "l18n", ["en_US"])
    assert refreshed.gettext("custom_crystal") == "Expedition crystal"
