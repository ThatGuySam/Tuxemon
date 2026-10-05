"""Build the separately authored conversation playground, without hardware writes."""

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def validate_content(content: dict) -> None:
    """Reject numeric coercion and unsafe spawn/exit locations before C emission."""

    def integer(value, maximum, field):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{field} must be an integer in 0..{maximum}")

    areas, npcs = content["areas"], content["npcs"]
    for field, maximum in (("flags", 255), ("items", 15)):
        for name, value in content.get(field, {}).items():
            integer(value, maximum, field + " " + name)
    if len(areas) != 4 or len(npcs) != 5:
        raise ValueError(
            "Playground requires four areas and five NPC scenarios"
        )
    for area in areas:
        rows = area["map"]
        if len(rows) != 14 or any(
            type(row) is not str or len(row) != 20 for row in rows
        ):
            raise ValueError("Maps must have fourteen twenty-column rows")
    footprints = []
    for i, npc in enumerate(npcs):
        integer(npc["area"], 3, "NPC area")
        integer(npc["x"], 15 if i == 0 else 17, "NPC x")
        integer(npc["y"], 9, "NPC y")
        if npc["x"] < 1 or npc["y"] < 1:
            raise ValueError("NPC must leave room for its art footprint")
        footprints.append(
            (npc["area"], npc["x"], npc["x"] + 2, npc["y"], npc["y"] + 4)
        )
        if i == 0:
            footprints.append(
                (
                    npc["area"],
                    npc["x"] + 3,
                    npc["x"] + 5,
                    npc["y"],
                    npc["y"] + 4,
                )
            )
        for reply in npc["replies"]:
            for field in ("requires_flags", "forbids_flags", "set_flags"):
                integer(reply.get(field, 0), 255, field)
            for field in ("requires_items", "spend_item", "give_item"):
                integer(reply.get(field, 0), 15, field)

    def position(area, x, y, field):
        integer(area, 3, field + " area")
        integer(x, 19, field + " x")
        integer(y, 13, field + " y")
        if areas[area]["map"][y][x] in "#~G":
            raise ValueError(field + " must be walkable")
        if any(
            area == a and left <= x < right and top <= y < bottom
            for a, left, right, top, bottom in footprints
        ):
            raise ValueError(field + " overlaps an NPC or companion")

    spawn = content.get("initial_state", {"area": 0, "x": 3, "y": 10})
    position(spawn["area"], spawn["x"], spawn["y"], "Initial position")
    integer(spawn.get("flags", 0), 255, "Initial flags")
    integer(spawn.get("inventory", 3), 15, "Initial inventory")
    for exit in content.get("exits", []):
        position(exit["area"], exit["x"], exit["y"], "Exit source")
        position(
            exit["to_area"], exit["to_x"], exit["to_y"], "Exit destination"
        )
        integer(exit.get("requires_flags", 0), 255, "Exit requires_flags")
    for consequence in content.get("world_consequences", []):
        integer(consequence["when_flags"], 255, "Consequence flags")
        gate = consequence.get("open_gate")
        if gate:
            integer(gate["area"], 3, "Gate area")
            integer(gate["x"], 19, "Gate x")
            integer(gate["y"], 13, "Gate y")


def verify_layout(noi: str, map_text: str, native_source: str) -> list[dict]:
    """Check every emitted WRAM section against the reserved absolute mailbox."""
    symbols = {}
    for line in noi.splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "DEF":
            symbols[words[1]] = int(words[2], 16)
    if symbols.get("_host_mailbox") != 0xC800:
        raise ValueError("Compiler symbols do not place host mailbox at C800")
    if not re.search(
        r"volatile\s+uint8_t\s+__at\(0xC800\)\s+host_mailbox\[1024\]\s*;",
        native_source,
    ):
        raise ValueError("Mailbox declaration must reserve exactly 1024 bytes")
    sections = []

    def check(name, start, length, origin):
        if length and start < 0xE000 and start + length > 0xC000:
            if start < 0xCC00 and start + length > 0xC800:
                raise ValueError(
                    f"{origin} WRAM section {name} overlaps host mailbox"
                )
            sections.append(
                {
                    "name": name,
                    "start": start,
                    "length": length,
                    "origin": origin,
                }
            )

    for name, start in symbols.items():
        if name.startswith("s__"):
            length_name = "l__" + name[3:]
            if length_name in symbols:
                check(name[3:], start, symbols[length_name], "NOI")
        elif (
            not name.startswith("l__")
            and 0xC800 <= start < 0xCC00
            and name != "_host_mailbox"
        ):
            raise ValueError(
                f"Absolute WRAM symbol {name} overlaps host mailbox"
            )
    for match in re.finditer(
        r"^([A-Za-z_][A-Za-z_0-9]*)\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s+=",
        map_text,
        re.MULTILINE,
    ):
        name, start, length = match.groups()
        check(name, int(start, 16), int(length, 16), "MAP")
    if not any(section["origin"] == "MAP" for section in sections):
        raise ValueError("Linker MAP contains no verifiable WRAM sections")
    if not any(section["origin"] == "NOI" for section in sections):
        raise ValueError("Compiler NOI contains no verifiable WRAM sections")
    return sections


def generate(
    repo: Path, output: Path, content_path: Path, compiler: Path | None = None
) -> Path:
    repo, output = repo.resolve(), output.resolve()
    spec = importlib.util.spec_from_file_location(
        "snapshot_rom", repo / "chromatic_demo/rom.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    content = json.loads(content_path.read_text())
    validate_content(content)
    npcs = content["npcs"]
    areas = content["areas"]
    if len(npcs) != 5 or len(areas) != 4:
        raise ValueError(
            "Playground requires four areas and five NPC scenarios"
        )

    def literal(value: str) -> str:
        if not isinstance(value, str) or any(
            ord(c) < 32 or ord(c) > 126 for c in value
        ):
            raise ValueError("Content must be printable ASCII")
        return json.dumps(value)

    header = [
        "/* Generated from explicitly authored test-world content. */",
        "#define NPC_COUNT 5",
        "#define AREA_COUNT 4",
        "#define REPLIES 6",
    ]
    header.append(
        "const char *const area_names[] = {"
        + ",".join(literal(a["name"][:18]) for a in areas)
        + "};"
    )
    for area in areas:
        rows = area["map"]
        if len(rows) != 14 or any(len(row) != 20 for row in rows):
            raise ValueError("Maps must have fourteen twenty-column rows")
    header.append(
        "const char area_maps[4][14][21] = {"
        + ",".join("{" + ",".join(map(literal, a["map"])) + "}" for a in areas)
        + "};"
    )
    header.append(
        "const char *const npc_names[] = {"
        + ",".join(literal(n["name"][:18]) for n in npcs)
        + "};"
    )
    for field in ("area", "x", "y"):
        header.append(
            f"const unsigned char npc_{field}[] = {{"
            + ",".join(str(n[field]) for n in npcs)
            + "};"
        )
    for i, npc in enumerate(npcs):
        if (
            not 0 <= npc["area"] < 4
            or not 1 <= npc["x"] <= 17
            or not 1 <= npc["y"] <= 9
        ):
            raise ValueError(f"NPC {i} outside safe art footprint")
        if i == 0 and npc["x"] > 15:
            raise ValueError(
                "Professor must leave room for the Rockitten companion footprint"
            )
        if len(npc["replies"]) != 6:
            raise ValueError("Each NPC requires exactly six guarded outcomes")
    spawn = content.get("initial_state", {"area": 0, "x": 3, "y": 10})
    companion = npcs[0]
    if (
        spawn["area"] == companion["area"]
        and companion["x"] + 3 <= spawn["x"] < companion["x"] + 5
        and companion["y"] <= spawn["y"] < companion["y"] + 4
    ):
        raise ValueError(
            "Initial player position overlaps the Rockitten companion"
        )
    header.append(
        "const char *const openings[] = {"
        + ",".join(literal(n["opening"]) for n in npcs)
        + "};"
    )
    for field in ("label", "text", "utterance"):
        header.append(
            f"const char *const reply_{field}[5][6] = {{"
            + ",".join(
                "{"
                + ",".join(
                    literal(
                        r.get("label_description", r[field])[:18]
                        if field == "label"
                        else r[field]
                    )
                    for r in n["replies"]
                )
                + "}"
                for n in npcs
            )
            + "};"
        )
    # Keep the seven-chip layout, but source its vocabulary from this NPC's
    # authored scenario. Exact quantities take priority when the scenario has them.
    keyword_chips = []
    for npc in npcs:
        vocabulary = list(npc.get("keywords", []))
        vocabulary += [
            word
            for reply in npc["replies"]
            for word in reply.get("keywords", [])
        ]
        preferred = [
            word for word in ("one", "two", "three") if word in vocabulary
        ]
        chosen = ["ask", "not"]
        for word in (
            preferred + vocabulary + ["help", "why", "name", "route", "status"]
        ):
            if word not in chosen and len(word) <= 18:
                literal(word)
                chosen.append(word)
            if len(chosen) == 7:
                break
        keyword_chips.append(chosen)
    header.append(
        "const char *const keyword_chips[5][7] = {"
        + ",".join(
            "{" + ",".join(map(literal, chips)) + "}"
            for chips in keyword_chips
        )
        + "};"
    )
    header.append(
        "const char *const reply_keywords[5][6] = {"
        + ",".join(
            "{"
            + ",".join(
                literal("|".join(r.get("keywords", []))) for r in n["replies"]
            )
            + "}"
            for n in npcs
        )
        + "};"
    )
    for field in (
        "requires_flags",
        "forbids_flags",
        "set_flags",
        "give_item",
        "requires_items",
        "spend_item",
    ):
        header.append(
            f"const unsigned char reply_{field}[5][6] = {{"
            + ",".join(
                "{"
                + ",".join(str(r.get(field, 0)) for r in n["replies"])
                + "}"
                for n in npcs
            )
            + "};"
        )
    exits = content.get("exits", [])
    header.append(f"#define EXIT_COUNT {len(exits)}")
    header.append(
        "const unsigned char exits[][7] = {"
        + ",".join(
            "{"
            + ",".join(
                str(e.get(k, 0))
                for k in (
                    "area",
                    "x",
                    "y",
                    "to_area",
                    "to_x",
                    "to_y",
                    "requires_flags",
                )
            )
            + "}"
            for e in exits
        )
        + "};"
    )
    art = b"".join(
        module.convert_sprite(repo / value["path"])
        for value in module.ASSETS.values()
    )
    header.append(
        "const unsigned char initial_state[] = {"
        + ",".join(
            str(content.get("initial_state", {}).get(k, d))
            for k, d in [
                ("area", 0),
                ("x", 3),
                ("y", 10),
                ("flags", 0),
                ("inventory", 3),
            ]
        )
        + "};"
    )
    header.append(
        "const unsigned char art_tiles[] = {" + ",".join(map(str, art)) + "};"
    )
    header.append(
        "const unsigned char professor_map[] = {192,193,194,195,196,197,198,199};"
    )
    header.append(
        "const unsigned char rockitten_map[] = {200,201,202,203,204,205,206,207};"
    )
    # A reproducible, authored eight-pixel traveller silhouette, not extracted Tuxemon art.
    hero = [
        0x18,
        0x18,
        0x3C,
        0x3C,
        0x18,
        0x18,
        0x7E,
        0x7E,
        0x5A,
        0x5A,
        0x18,
        0x18,
        0x24,
        0x24,
        0x42,
        0x42,
    ]
    header.append(
        "const unsigned char player_tiles[] = {"
        + ",".join(map(str, hero))
        + "};"
    )
    terrain = (
        [0, 0] * 8
        + [
            255,
            255,
            129,
            129,
            165,
            165,
            129,
            129,
            255,
            255,
            24,
            24,
            24,
            24,
            24,
            24,
        ]
        + [0, 0, 0, 0, 16, 0, 8, 0, 0, 0, 1, 0, 2, 0, 0, 0]
        + [0, 85, 170, 0, 0, 0, 85, 0, 0, 170, 0, 0, 170, 0, 0, 0]
        + [
            129,
            129,
            129,
            129,
            255,
            255,
            129,
            129,
            129,
            129,
            255,
            255,
            129,
            129,
            129,
            129,
        ]
    )
    header.append(
        "const unsigned char terrain_tiles[] = {"
        + ",".join(map(str, terrain))
        + "};"
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "playground_assets.h").write_text("\n".join(header) + "\n")
    source = Path(__file__).parent / "native/playground.c"
    (output / "playground.c").write_bytes(source.read_bytes())
    compiler = compiler or module.DEFAULT_COMPILER
    rom = output / "playground.gbc"
    command = [
        str(compiler),
        "-Wm-yC",
        "-Wm-ynCHATPLAYGROUND",
        "-Wl-j",
        "-Wl-m",
        "-o",
        str(rom),
        str(output / "playground.c"),
    ]
    subprocess.run(command, cwd=output, check=True, timeout=60)
    symbols = (output / "playground.noi").read_text()
    # Absolute mailbox must retain a stable address for the host emulator bridge.
    layout = verify_layout(
        symbols, (output / "playground.map").read_text(), source.read_text()
    )
    provenance = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "rom_sha256": module.sha256(rom),
        "content_sha256": module.sha256(content_path),
        "content_source": str(content_path.resolve()),
        "content": content,
        "dialogue_source": "explicitly authored fictional test world, not Tuxemon canon",
        "prediction_source": "authored deterministic candidates, not model results",
        "compiler_command": command,
        "mailbox_address": "0xC800",
        "mailbox_length": 1024,
        "wram_layout": layout,
        "linker_noi_sha256": module.sha256(output / "playground.noi"),
        "linker_map_sha256": module.sha256(output / "playground.map"),
        "hardware_verified": False,
        "physical_actions": "none",
        "assets": [
            {
                **a,
                "sha256": module.sha256(repo / a["path"]),
                "license": "CC-BY-SA-4.0",
                "transformation": "front idle frame cropped and quantized by existing rom.convert_sprite",
            }
            for a in module.ASSETS.values()
        ],
        "generated_art": {
            "traveller": hero,
            "terrain_tiles": terrain,
            "method": "deterministic authored byte silhouette, wall, grass, water and gate patterns",
        },
    }
    (output / "playground-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    return rom


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    print(generate(args.repo, args.output, args.content, args.compiler))


if __name__ == "__main__":
    main()
