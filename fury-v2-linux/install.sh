#!/bin/sh
set -eu
cd "$(dirname "$(realpath "$0")")"
if python3 -c 'import PyQt6.QtWidgets' >/dev/null 2>&1; then
    python3 install-launcher.py
else
    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python install-launcher.py
fi
printf '%s\n' 'Готово. Открой Fury V2 Linux из меню приложений или запусти ./run.sh.'
