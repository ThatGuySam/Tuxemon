"""Finite verification of the real CLI launcher; normal loop stays unchanged."""

import json
import sys
from pathlib import Path

import pygame

import run_tuxemon

original_display = run_tuxemon.init_display
custom = "--custom-game" in sys.argv[1:]


def finite_loop(client):
    from tuxemon.session import local_session

    for _ in range(100):
        client.update(1 / 60)
        client.draw()
    if custom:
        assert client.get_map_name() == "custom_last_ascent.tmx"
        assert local_session.player.tile_pos == (4, 7)
        pygame.event.post(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, unicode="")
        )
        for _ in range(32):
            client.update(1 / 60)
            client.draw()
        pygame.event.post(
            pygame.event.Event(pygame.KEYUP, key=pygame.K_UP, unicode="")
        )
        client.update(1 / 60)
        pygame.event.post(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="")
        )
        client.update(1 / 60)
        client.draw()
        assert client.current_state.name == "CustomConversationState"
        assert client.custom_scenario.npc == 0
    else:
        assert not hasattr(client, "custom_scenario")
        assert any(
            name in client.active_state_names
            for name in ("IntroState", "SplashState", "StartState")
        )
    destination = Path("work/custom-game-evidence")
    destination.mkdir(parents=True, exist_ok=True)
    mode = "custom" if custom else "normal"
    pygame.image.save(client.screen, destination / f"00-cli-{mode}.png")
    (destination / f"cli-{mode}.json").write_text(
        json.dumps(
            {
                "entrypoint": "run_tuxemon.launch_game",
                "argv": sys.argv[1:],
                "states": list(client.active_state_names),
                "frames": client.frame_number,
                "render": "SDL Pygame actual client",
                "inference": "none",
            },
            indent=2,
        )
        + "\n"
    )
    print("CLI_LAUNCH_PASS", mode, list(client.active_state_names))
    client.network_manager.shutdown()


def display(mode):
    context = original_display(mode)
    # Match the real launcher's import order; finite test loop replaces only
    # the unbounded loop. State/movement/event/render implementations are real.
    from tuxemon.client import LocalPygameClient
    from tuxemon.network.manager import NetworkManager

    NetworkManager.initialize = lambda self: None
    LocalPygameClient.main = finite_loop
    return context


run_tuxemon.init_display = display
run_tuxemon.launch_game(sys.argv[1:])
