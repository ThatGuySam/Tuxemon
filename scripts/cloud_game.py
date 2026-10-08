"""Run repository commands with isolated cloud storage and no home writes."""

import os
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
from tuxemon.platform import platform

storage = root / "work" / "userdata"
original_init = platform.init


def cloud_init():
    original_init()
    platform.user_storage.user_dir = lambda: storage
    platform.user_storage.ensure_dirs()


platform.init = cloud_init
platform.user_storage.user_dir = lambda: storage
cloud_init()
mode, *args = sys.argv[1:]
sys.argv = [mode, *args]
if mode == "pytest":
    runpy.run_module("pytest", run_name="__main__")
else:
    runpy.run_path(str(root / mode), run_name="__main__")
