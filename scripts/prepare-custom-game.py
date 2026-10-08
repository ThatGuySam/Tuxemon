"""Compile repository translations before initializing database validators."""

from tuxemon.locale.locale import T

T.initialize_translations(recompile=True)
print("Repository translations compiled; start the game in a fresh process.")
