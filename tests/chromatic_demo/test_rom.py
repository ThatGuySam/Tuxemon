"""Verify source reading, bounds, and lossless page reconstruction."""

# SPDX-License-Identifier: GPL-3.0-or-later
import json
import sys
import tempfile
import unittest
from pathlib import Path

from chromatic_demo.rom import (
    authored_dialogue,
    convert_sprite,
    generate,
    paginate,
    sha256,
)

REPO = Path(__file__).resolve().parents[2]


class RomTests(unittest.TestCase):
    """Exercise behavior required by the constrained handheld screen."""

    def test_authored_lines_are_real_translation_entries(self) -> None:
        """The source fallback must match the selected fork translations."""
        replies = authored_dialogue(REPO)
        self.assertEqual(
            replies["rockitten"],
            "Professor: A superb choice! Rockitten is an earth Tuxemon.",
        )
        self.assertIn("little animals", replies["greet"])

    def test_paginate_preserves_all_words(self) -> None:
        """Paging must keep every authored word within display bounds."""
        for reply in authored_dialogue(REPO).values():
            pages = paginate(reply)
            self.assertTrue(all(len(page) <= 6 for page in pages))
            self.assertTrue(
                all(len(line) <= 18 for page in pages for line in page)
            )
            self.assertEqual(
                " ".join(reply.split()),
                " ".join(line for page in pages for line in page),
            )

    def test_invalid_generated_reply_is_rejected(self) -> None:
        """Bounds and unrepresentable text fail before compilation."""
        for invalid in ("", "x" * 601, "control\x00text", "Unicode \u2603"):
            with (
                self.subTest(invalid=invalid[:20]),
                self.assertRaises(ValueError),
            ):
                paginate(invalid)

    def test_sprite_frame_encodes_eight_tiles(self) -> None:
        """The real source idle frame encodes 16 by 32 pixels."""
        encoded = convert_sprite(REPO / "mods/tuxemon/sprites/professor.png")
        self.assertEqual(len(encoded), 8 * 16)
        self.assertGreater(len(set(encoded)), 1)

    def test_supplied_text_cannot_claim_authored_or_generated_origin(self):
        """Check provenance at a synthetic external-compiler boundary."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "imported-authored-translations.json"
            replies = authored_dialogue(REPO)
            source.write_text(json.dumps(replies))
            compiler = root / "synthetic-compiler-boundary"
            compiler.write_text(
                "#!" + sys.executable + "\n"
                "from pathlib import Path\n"
                "import sys\n"
                "Path(sys.argv[sys.argv.index('-o') + 1]).write_bytes("
                "b'SYNTHETIC UNIT FIXTURE: NOT A PLAYABLE ROM')\n"
            )
            compiler.chmod(0o700)
            generate(
                REPO,
                root / "build",
                replies,
                "chatgpt",
                "TEST-ONLY-MODEL",
                compiler=compiler,
                snapshot_source=source,
            )
            provenance = json.loads(
                (root / "build/provenance.json").read_text()
            )
            self.assertEqual(provenance["provider"], "imported")
            self.assertEqual(
                provenance["snapshot_source"]["sha256"],
                sha256(source),
            )
            self.assertIn(
                "IMPORTED SNAPSHOT",
                (root / "build/assets.h").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
