"""Verify all nine complete conversations using the shared frame-checked driver."""

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
from pathlib import Path

from verify_screen_frames import verify

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bridge", type=Path)
    parser.add_argument("--picker-model", type=Path)
    args = parser.parse_args()
    verify(
        args.build,
        args.output_dir,
        bridge_path=args.bridge,
        interfaces=True,
        picker_model=args.picker_model,
    )
