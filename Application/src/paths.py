"""Runtime paths for source and packaged AnonRad AI builds."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


APP_NAME = "AnonRadAI"


def bundled_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return bundled_root()
    return Path(__file__).resolve().parents[2]


def user_config_root() -> Path:
    override = os.environ.get("ANONRAD_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA")
        return Path(base).expanduser() / APP_NAME if base else Path.home() / f".{APP_NAME}"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def bundled_path(*parts: str) -> Path:
    return bundled_root().joinpath(*parts)
