# Packaging AnonRad AI

Run each build on the target operating system. PyInstaller does not reliably cross-compile GUI apps.

## macOS

```bash
cd Application
packaging/build_macos_dmg.sh
```

Output:

```text
Application/dist/AnonRad-AI-macOS.dmg
```

## Windows

Run in PowerShell from the project root or from `Application`:

```powershell
cd Application
powershell -ExecutionPolicy Bypass -File packaging\build_windows_installer.ps1
```

Output:

- PyInstaller folder: `Application/dist/AnonRad AI/`
- Inno Setup installer, if `ISCC.exe` is installed: `Application/packaging/Output/AnonRad-AI-Windows-Setup.exe`

## Linux Debian Package

```bash
cd Application
packaging/build_linux_deb.sh
```

Output:

```text
Application/dist/anonrad-ai_1.0.0_<arch>.deb
```

## Included Assets

The PyInstaller spec bundles:

- `Application/resources/`
- `Application/config/`
- `Model/runs/radiograph_phi_detection/augmented/weights/best.pt`

Editable OCR rules are copied to the user's config folder on first launch in packaged builds.

## Notes

- Build on a clean machine or clean virtual environment.
- The first OCR use can still need EasyOCR model files unless they are already cached or explicitly bundled later.
- For hospital deployment, signing/notarization is recommended:
  - macOS: codesign + notarization.
  - Windows: Authenticode signing.
  - Linux: repository signing or signed package distribution.
