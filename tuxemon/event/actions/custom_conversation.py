# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass

from tuxemon.event.eventaction import EventAction


@dataclass
class CustomConversationAction(EventAction):
    """TMX interaction hook. No campaign enables this action implicitly."""

    name = "custom_conversation"
    npc_index: int

    def start(self, session):
        from tuxemon.custom_game.runtime import Scenario

        client = session.client
        if client.get_map_name() != "custom_last_ascent.tmx":
            self.stop()
            return
        if not 0 <= self.npc_index < 5:
            raise ValueError("Unknown custom NPC")
        if not hasattr(client, "custom_scenario"):
            client.custom_scenario = Scenario(client)
            if not session.player.game_variables.has("custom_ascent_flags"):
                client.custom_scenario.reset_story()
        client.custom_scenario.select_npc(self.npc_index)
        client.push_state("CustomConversationState")
        self.stop()
