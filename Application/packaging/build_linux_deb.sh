#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$(cd "$APP_DIR/.." && pwd)"
BUILD_ENV="$APP_DIR/.build_env"
PACKAGE_NAME="anonrad-ai"
VERSION="1.0.0"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
DIST_DIR="$APP_DIR/dist"
PKG_ROOT="$APP_DIR/build/${PACKAGE_NAME}_${VERSION}_${ARCH}"

if [ "$(uname -s)" != "Linux" ]; then
  echo "This script must be run on Linux."
  exit 1
fi

if [ ! -f "$PROJECT_DIR/Model/runs/radiograph_phi_detection/augmented/weights/best.pt" ]; then
  echo "Missing YOLO model: Model/runs/radiograph_phi_detection/augmented/weights/best.pt"
  exit 1
fi

cd "$APP_DIR"

python3 -m venv "$BUILD_ENV"
"$BUILD_ENV/bin/python" -m pip install --upgrade pip
"$BUILD_ENV/bin/python" -m pip install -r requirements.txt -r packaging/requirements-build.txt

rm -rf build dist
"$BUILD_ENV/bin/pyinstaller" --noconfirm packaging/anonrad_ai.spec

rm -rf "$PKG_ROOT"
mkdir -p "$PKG_ROOT/DEBIAN" "$PKG_ROOT/opt/anonrad-ai" "$PKG_ROOT/usr/share/applications" "$PKG_ROOT/usr/bin"
cp -R "$DIST_DIR/AnonRad AI/." "$PKG_ROOT/opt/anonrad-ai/"

cat > "$PKG_ROOT/DEBIAN/control" <<CONTROL
Package: $PACKAGE_NAME
Version: $VERSION
Section: graphics
Priority: optional
Architecture: $ARCH
Maintainer: AnonRad AI
Description: Local AI radiograph anonymization desktop application.
CONTROL

cat > "$PKG_ROOT/usr/share/applications/anonrad-ai.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=AnonRad AI
Comment=Local AI radiograph anonymization
Exec=/usr/bin/anonrad-ai
Terminal=false
Categories=Graphics;MedicalSoftware;
DESKTOP

cat > "$PKG_ROOT/usr/bin/anonrad-ai" <<LAUNCHER
#!/bin/bash
exec "/opt/anonrad-ai/AnonRad AI" "\$@"
LAUNCHER
chmod +x "$PKG_ROOT/usr/bin/anonrad-ai"

dpkg-deb --build "$PKG_ROOT" "$DIST_DIR/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo "Created: $DIST_DIR/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
