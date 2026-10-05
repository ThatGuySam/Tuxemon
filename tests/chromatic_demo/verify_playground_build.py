"""Check actual build layout and rejected content/forged overlap regressions."""

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path


def verify(build: Path) -> None:
    path = Path(__file__).resolve().parents[2] / "chromatic_demo/playground.py"
    spec = importlib.util.spec_from_file_location("playground_builder", path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    content = json.loads((build / "playground-provenance.json").read_text())[
        "content"
    ]
    noi = (build / "playground.noi").read_text()
    map_text = (build / "playground.map").read_text()
    source = (build / "playground.c").read_text()
    builder.validate_content(content)
    layout = builder.verify_layout(noi, map_text, source)
    checks = []

    def rejected(name, operation):
        try:
            operation()
        except ValueError:
            checks.append(name)
        else:
            raise AssertionError(name + " was accepted")

    for bad in (True, "1", 1.5, -1, 256):
        modified = copy.deepcopy(content)
        modified["npcs"][0]["replies"][0]["set_flags"] = bad
        rejected(
            f"invalid flag {bad!r}",
            lambda modified=modified: builder.validate_content(modified),
        )
    for field, value in (
        ("give_item", 16),
        ("spend_item", False),
        ("requires_items", "2"),
    ):
        modified = copy.deepcopy(content)
        modified["npcs"][1]["replies"][0][field] = value
        rejected(
            "invalid " + field,
            lambda modified=modified: builder.validate_content(modified),
        )
    for field, value in (("area", 4), ("x", 20), ("y", 14), ("x", True)):
        modified = copy.deepcopy(content)
        modified["initial_state"][field] = value
        rejected(
            "invalid initial " + field + repr(value),
            lambda modified=modified: builder.validate_content(modified),
        )
    modified = copy.deepcopy(content)
    modified["initial_state"].update(area=0, x=0, y=0)
    rejected(
        "spawn in wall",
        lambda modified=modified: builder.validate_content(modified),
    )
    modified = copy.deepcopy(content)
    npc = modified["npcs"][0]
    modified["initial_state"].update(area=npc["area"], x=npc["x"], y=npc["y"])
    rejected(
        "spawn inside NPC",
        lambda modified=modified: builder.validate_content(modified),
    )
    modified = copy.deepcopy(content)
    modified["exits"][0]["to_area"] = 4
    rejected(
        "exit invalid destination area",
        lambda modified=modified: builder.validate_content(modified),
    )
    modified = copy.deepcopy(content)
    modified["exits"][0].update(to_area=0, to_x=0, to_y=0)
    rejected(
        "exit destination wall",
        lambda modified=modified: builder.validate_content(modified),
    )
    modified = copy.deepcopy(content)
    modified["exits"][0].update(area=npc["area"], x=npc["x"] + 3, y=npc["y"])
    rejected(
        "exit source inside companion",
        lambda modified=modified: builder.validate_content(modified),
    )
    modified = copy.deepcopy(content)
    modified["exits"][0]["requires_flags"] = True
    rejected(
        "exit bool mask",
        lambda modified=modified: builder.validate_content(modified),
    )
    # Forge additional allocated sections in each actual linker product independently.
    rejected(
        "NOI DATA overflow",
        lambda: builder.verify_layout(
            noi + "\nDEF s__FORGED 0xC7F0\nDEF l__FORGED 0x20\n",
            map_text,
            source,
        ),
    )
    rejected(
        "MAP section overflow",
        lambda: builder.verify_layout(
            noi,
            map_text + "\n_FORGED 0000C7F0 00000020 = 32. bytes (REL,CON)\n",
            source,
        ),
    )
    rejected(
        "absolute symbol collision",
        lambda: builder.verify_layout(
            noi + "\nDEF _evil 0xC801\n", map_text, source
        ),
    )
    rejected(
        "wrong mailbox extent",
        lambda: builder.verify_layout(
            noi,
            map_text,
            source.replace("host_mailbox[1024]", "host_mailbox[1023]"),
        ),
    )
    report = {
        "verified_actual_layout": layout,
        "rejected_regressions": checks,
        "fixtures": "Invalid copies and forged linker additions are explicit negative-test fixtures, not build measurements.",
    }
    (build / "playground-build-verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(
        f"Build layout and {len(checks)} invalid-content/overlap regressions verified."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    verify(parser.parse_args().build)
