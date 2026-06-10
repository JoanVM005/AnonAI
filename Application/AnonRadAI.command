#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [ ! -d ".anonrad_env" ]; then
  python3 -m venv .anonrad_env
  .anonrad_env/bin/python -m pip install --upgrade pip
  .anonrad_env/bin/python -m pip install -r requirements.txt
fi

.anonrad_env/bin/python src/app.py
