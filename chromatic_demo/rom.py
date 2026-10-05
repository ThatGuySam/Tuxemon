"""Build a native GBC dialogue snapshot from real Tuxemon fork content."""

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

DEFAULT_COMPILER = (
    Path.home()
    / "Library/Application Support/modretro-chromatic/toolchain/.local/gbdk/bin/lcc"
)
INTENTS = {
    "greet": ("Hello", "professor_dialog"),
    "rockitten": ("About Rockitten", "professor_dialog6.2"),
    "farewell": ("Say goodbye", "professor_dialog7"),
}
MAX_REPLY = 600
PAGE_LINES = 6
LINE_COLUMNS = 18
ASSETS = {
    "professor": {
        "path": "mods/tuxemon/sprites/professor.png",
        "authors": ["Kurt Stine"],
        "credit_lines": [54, 56],
    },
    "rockitten": {
        "path": "mods/tuxemon/sprites/rockitten.png",
        "authors": ["tamashihoshi"],
        "credit_lines": [553, 555],
    },
}


def sha256(path: Path) -> str:
    """Return the content digest of an existing file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authored_dialogue(repo: Path) -> dict[str, str]:
    """Read exact English translation entries selected for the demo."""
    po = repo / "mods/tuxemon/l18n/en_US/LC_MESSAGES/base.po"
    translations = {}
    wanted = {key for _, key in INTENTS.values()}
    for block in po.read_text(encoding="utf-8").split("\n\n"):
        if not any(f'msgid "{key}"\n' in block for key in wanted):
            continue
        key = None
        value = []
        reading_value = False
        for line in block.splitlines():
            if line.startswith("msgid "):
                key = ast.literal_eval(line[6:])
            elif line.startswith("msgstr "):
                reading_value = True
                value.append(ast.literal_eval(line[7:]))
            elif reading_value and line.startswith('"'):
                value.append(ast.literal_eval(line))
        if key is not None:
            translations[key] = "".join(value)
    return {intent: translations[key] for intent, (_, key) in INTENTS.items()}


def paginate(text: str) -> list[list[str]]:
    """Validate a complete reply and wrap it to six 18-column lines."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Dialogue must be a nonempty string")
    if len(text) > MAX_REPLY:
        raise ValueError(f"Dialogue exceeds {MAX_REPLY} characters")
    if any(
        ord(char) > 126 or (ord(char) < 32 and char not in "\n\t")
        for char in text
    ):
        raise ValueError("ROM dialogue requires printable ASCII text")
    lines = textwrap.wrap(
        " ".join(text.split()),
        width=LINE_COLUMNS,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return [
        lines[index : index + PAGE_LINES]
        for index in range(0, len(lines), PAGE_LINES)
    ]


def convert_sprite(path: Path) -> bytes:
    """Encode the real front idle 16 by 32 frame as Game Boy 2bpp tiles."""
    with Image.open(path) as source:
        if source.size != (48, 128):
            raise ValueError(f"Unexpected sprite sheet size: {path}")
        sprite = source.convert("RGBA").crop((16, 0, 32, 32))
    pixels = []
    for red, green, blue, alpha in sprite.get_flattened_data():
        if alpha < 128 or (red, green, blue) == (255, 0, 255):
            pixels.append(0)
        else:
            luminance = (299 * red + 587 * green + 114 * blue) // 1000
            pixels.append(3 - min(3, luminance // 64))
    encoded = bytearray()
    for tile_y in range(4):
        for tile_x in range(2):
            for row in range(8):
                low = high = 0
                for column in range(8):
                    color = pixels[
                        (tile_y * 8 + row) * 16 + tile_x * 8 + column
                    ]
                    low |= (color & 1) << (7 - column)
                    high |= ((color >> 1) & 1) << (7 - column)
                encoded.extend((low, high))
    return bytes(encoded)


def c_string(text: str) -> str:
    """Produce a C string literal from validated ASCII text."""
    return json.dumps(text, ensure_ascii=True)


def generate(
    repo: Path,
    output: Path,
    snapshot_replies: dict[str, str] | None = None,
    provider: str = "offline",
    model: str | None = None,
    compiler: Path | None = None,
    snapshot_source: Path | None = None,
    generation_receipt: dict | None = None,
) -> Path:
    """Build a ROM and provenance for authored or real generated snapshots."""
    if provider not in ("offline", "imported", "chatgpt", "ollama"):
        raise ValueError("Unknown dialogue provider")
    if provider in ("chatgpt", "ollama") and (
        not snapshot_replies or not model
    ):
        raise ValueError("Generated snapshots require replies and a model")
    if snapshot_replies is not None and generation_receipt is None:
        provider = "imported"
    if provider == "imported" and snapshot_replies is None:
        raise ValueError("Imported snapshots require supplied replies")
    repo = repo.resolve()
    output = output.resolve()
    authored = authored_dialogue(repo)
    if snapshot_replies is not None:
        if set(snapshot_replies) != set(INTENTS):
            raise ValueError("Replies must contain greet, rockitten, farewell")
        replies = snapshot_replies
    else:
        replies = authored
    pages = [paginate(replies[intent]) for intent in INTENTS]
    output.mkdir(parents=True, exist_ok=True)
    art = b"".join(
        convert_sprite(repo / spec["path"]) for spec in ASSETS.values()
    )
    max_pages = max(map(len, pages))
    header = [
        "/* SPDX-License-Identifier: GPL-3.0-or-later */",
        "#define INTENT_COUNT 3",
        f"#define PAGE_LINES {PAGE_LINES}",
        "#define ART_TILE_COUNT 16",
        '#define PROVIDER_LABEL "' + provider.upper() + ' SNAPSHOT"',
        '#define SNAPSHOT_LABEL "'
        + (
            "AUTHORED OFFLINE"
            if provider == "offline"
            else "PRECOMPILED REPLY"
        )
        + '"',
        "const unsigned char art_tiles[] = {" + ",".join(map(str, art)) + "};",
        "const unsigned char professor_map[] = {"
        + ",".join(map(str, range(128, 136)))
        + "};",
        "const unsigned char rockitten_map[] = {"
        + ",".join(map(str, range(136, 144)))
        + "};",
        "const char * const intent_labels[] = {"
        + ",".join(c_string(value[0]) for value in INTENTS.values())
        + "};",
        "const unsigned char page_counts[] = {"
        + ",".join(str(len(item)) for item in pages)
        + "};",
        f"const char * const dialogue_pages[3][{max_pages}][6] = {{",
    ]
    for intent_pages in pages:
        header.append("{")
        for page in intent_pages:
            padded = page + [""] * (PAGE_LINES - len(page))
            header.append("{" + ",".join(map(c_string, padded)) + "},")
        header.append("},")
    header.append("};")
    (output / "assets.h").write_text("\n".join(header) + "\n")
    template = Path(__file__).parent / "native/demo.c"
    (output / "demo.c").write_bytes(template.read_bytes())
    rom = output / "demo.gbc"
    compiler = compiler or Path(
        os.environ.get(
            "GBDK_LCC",
            str(DEFAULT_COMPILER),
        )
    )
    command = [
        str(compiler),
        "-Wm-yC",
        "-Wm-ynTUXEMONPROTO",
        "-Wl-j",
        "-o",
        str(rom),
        str(output / "demo.c"),
    ]
    subprocess.run(command, check=True, cwd=output, timeout=60)
    baseline = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
        timeout=10,
    ).stdout.strip()
    translation = "mods/tuxemon/l18n/en_US/LC_MESSAGES/base.po"
    provenance = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "fork": "https://github.com/ThatGuySam/Tuxemon",
        "baseline_commit": baseline,
        "provider": provider,
        "model": model,
        "reply_source": (
            "repository-authored translations"
            if provider == "offline"
            else "caller supplied replies"
        ),
        "generation_receipt": generation_receipt,
        "snapshot_source": {
            "path": str(snapshot_source.resolve()),
            "sha256": sha256(snapshot_source),
        }
        if snapshot_source
        else None,
        "delivery": "precompiled snapshot, no runtime network access",
        "dialogue": {
            intent: {
                "authored_key": INTENTS[intent][1],
                "authored_context": authored[intent],
                "request": {
                    "npc": "Professor",
                    "intent": intent,
                    "authored_context": authored[intent],
                }
                if provider != "offline"
                else None,
                "displayed_reply": replies[intent],
                "pages": pages[index],
            }
            for index, intent in enumerate(INTENTS)
        },
        "translation_source": {
            "path": translation,
            "sha256": sha256(repo / translation),
        },
        "assets": [
            {
                **spec,
                "sha256": sha256(repo / spec["path"]),
                "license": "CC-BY-SA-4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "transformation": (
                    "crop front idle frame (16,0,32,32); alpha/fuchsia to white; "
                    "weighted RGB luminance quantized to four shades; 2bpp tiles"
                ),
            }
            for spec in ASSETS.values()
        ],
        "code_license": "GPL-3.0-or-later",
        "compiler": {"path": str(compiler), "command": command},
        "rom_sha256": sha256(rom),
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n",
        encoding="utf-8",
    )
    return rom


def main() -> None:
    """Generate an offline ROM or a user-selected model dialogue snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dialogue-json", type=Path)
    parser.add_argument(
        "--provider",
        choices=("offline", "chatgpt", "ollama"),
        default="offline",
    )
    parser.add_argument("--model")
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    replies = None
    receipt = None
    if args.dialogue_json:
        if args.provider != "offline":
            parser.error("--dialogue-json cannot assert a model provider")
        replies = json.loads(args.dialogue_json.read_text())
    elif args.provider != "offline":
        if not args.model:
            parser.error("--model is required for model-generated snapshots")
        from chromatic_demo.providers import (
            ChatGPTProvider,
            OllamaProvider,
            prompt,
        )

        selected = (
            ChatGPTProvider(args.model)
            if args.provider == "chatgpt"
            else OllamaProvider(args.model)
        )
        replies = {
            intent: selected.reply("Professor", intent, context)
            for intent, context in authored_dialogue(args.repo).items()
        }
        receipt = {
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider": args.provider,
            "model": args.model,
            "provider_module_sha256": sha256(
                Path(__file__).parent / "providers.py"
            ),
            "prompts": {
                intent: prompt("Professor", intent, context)
                for intent, context in authored_dialogue(args.repo).items()
            },
        }
    print(
        generate(
            args.repo,
            args.output,
            replies,
            args.provider,
            args.model,
            args.compiler,
            args.dialogue_json,
            receipt,
        )
    )


if __name__ == "__main__":
    main()
