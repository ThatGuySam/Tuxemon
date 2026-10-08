# SPDX-License-Identifier: GPL-3.0-or-later
"""Names and controls for the opt-in camp, drawn by WorldState."""

import pygame

from tuxemon.map.map import get_pos_from_tilepos
from tuxemon.math import Vector2


def draw_camp(client, surface):
    if not hasattr(client, "custom_camp_font"):
        client.custom_camp_font = pygame.font.Font(
            None, max(16, surface.get_height() // 30)
        )
    font = client.custom_camp_font
    for index, npc in enumerate(client.custom_scenario.world["npcs"]):
        entity = client.get_npc(f"custom_ascent_{index}")
        if entity is None:
            continue
        x, y = get_pos_from_tilepos(
            client.map_manager.current_map,
            client.context,
            Vector2(entity.tile_pos),
        )
        label = font.render(npc["name"], True, (235, 244, 240), (15, 23, 35))
        surface.blit(label, (x, y + client.context.tile_size[1] // 2))
    title = font.render(
        "The Last Ascent | authored custom scenario",
        True,
        (125, 220, 198),
        (15, 23, 35),
    )
    surface.blit(title, (12, 10))
    help_text = font.render(
        "Arrows/D-pad walk. Face a person, Return/A talks.",
        True,
        (245, 215, 140),
        (15, 23, 35),
    )
    surface.blit(help_text, (12, surface.get_height() - 28))
