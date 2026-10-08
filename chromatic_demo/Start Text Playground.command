#!/bin/zsh
set -eu
cd "${0:A:h:h}"
python_path="${CHROMATIC_PYTHON:-$PWD/venv/chromatic/bin/python}"
if [[ ! -x "$python_path" ]]; then
  print -u2 'Set CHROMATIC_PYTHON to the Chromatic Python interpreter, or create venv/chromatic.'
  exit 1
fi
if (( $# == 0 )); then
  exec "$python_path" -m chromatic_demo.terminal --provider ollama --model gemma4:26b-mlx
else
  exec "$python_path" -m chromatic_demo.terminal "$@"
fi
