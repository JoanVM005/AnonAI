#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$(cd "$APP_DIR/.." && pwd)"
DIST_DIR="$APP_DIR/dist"
BUILD_ENV="$APP_DIR/.build_env"
APP_NAME="AnonRad AI"
DMG_NAME="AnonRad-AI-macOS.dmg"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This script must be run on macOS."
  exit 1
fi

cd "$APP_DIR"

if [ ! -f "$PROJECT_DIR/Model/runs/radiograph_phi_detection/augmented/weights/best.pt" ]; then
  echo "Missing YOLO model: Model/runs/radiograph_phi_detection/augmented/weights/best.pt"
  exit 1
fi

python3 -m venv "$BUILD_ENV"
"$BUILD_ENV/bin/python" -m pip install --upgrade pip
"$BUILD_ENV/bin/python" -m pip install -r requirements.txt -r packaging/requirements-build.txt

rm -rf build dist
"$BUILD_ENV/bin/pyinstaller" --noconfirm packaging/anonrad_ai.spec

rm -f "$DIST_DIR/$DMG_NAME"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DIST_DIR/$APP_NAME.app" \
  -ov \
  -format UDZO \
  "$DIST_DIR/$DMG_NAME"

echo "Created: $DIST_DIR/$DMG_NAME"
