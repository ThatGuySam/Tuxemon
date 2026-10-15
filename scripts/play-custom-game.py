"""Launch the single-player conversation scenario without a multiplayer server."""

import run_tuxemon

original_display = run_tuxemon.init_display


def display(mode):
    context = original_display(mode)
    from tuxemon.network.manager import NetworkManager

    NetworkManager.initialize = lambda self: None
    return context


run_tuxemon.init_display = display
run_tuxemon.launch_game(["--custom-game"])
