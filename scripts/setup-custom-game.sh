#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p work
python3 -m venv work/venv
UV_CACHE_DIR="$PWD/work/uv-cache" uv pip sync --python work/venv/bin/python scripts/custom-game-requirements.lock
# SDL dummy works without system packages. Xvfb is optional for an X11 run.
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy work/venv/bin/python scripts/cloud_game.py scripts/prepare-custom-game.py
