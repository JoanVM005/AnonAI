"""Persistent OCR regex rule management for the local application."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from paths import bundled_path, user_config_root

BUNDLED_DEFAULT_RULES_PATH = bundled_path("config", "ocr_rules.json")
DEFAULT_RULES_PATH = (
    user_config_root() / "ocr_rules.json"
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1] / "config" / "ocr_rules.json"
)


def new_rule(name: str = "", pattern: str = "", enabled: bool = True) -> dict:
    return {
        "id": uuid4().hex,
        "name": name.strip(),
        "pattern": pattern.strip(),
        "enabled": bool(enabled),
    }


def validate_regex(pattern: str) -> None:
    if not pattern.strip():
        raise ValueError("La expresion regular no puede estar vacia.")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Regex no valida: {exc}") from exc


def normalize_rule(raw_rule: dict) -> dict:
    name = str(raw_rule.get("name", "")).strip()
    pattern = str(raw_rule.get("pattern", "")).strip()
    if not name:
        raise ValueError("El nombre de la regla no puede estar vacio.")
    validate_regex(pattern)
    return {
        "id": str(raw_rule.get("id") or uuid4().hex),
        "name": name,
        "pattern": pattern,
        "enabled": bool(raw_rule.get("enabled", True)),
    }


def load_ocr_rules(path: Path = DEFAULT_RULES_PATH) -> list[dict]:
    if not path.exists():
        if BUNDLED_DEFAULT_RULES_PATH.exists() and BUNDLED_DEFAULT_RULES_PATH != path:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BUNDLED_DEFAULT_RULES_PATH, path)
        else:
            save_ocr_rules([], path)
    if not path.exists():
        save_ocr_rules([], path)
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_rules = data.get("rules", []) if isinstance(data, dict) else []
    rules: list[dict] = []
    for raw_rule in raw_rules:
        try:
            rules.append(normalize_rule(raw_rule))
        except ValueError:
            continue
    return rules


def save_ocr_rules(rules: list[dict], path: Path = DEFAULT_RULES_PATH) -> None:
    normalized = [normalize_rule(rule) for rule in rules]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rules": normalized}, indent=2), encoding="utf-8")


def enabled_rules(rules: list[dict]) -> list[dict]:
    return [rule for rule in rules if rule.get("enabled")]
