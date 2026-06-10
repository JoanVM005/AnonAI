"""OCR-assisted redaction driven only by enabled regex rules."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

import numpy as np
from PIL import Image

try:
    import easyocr
except Exception:
    easyocr = None


_READER = None


@dataclass
class OCRDetection:
    rule_id: str
    rule_name: str
    confidence: float
    box_xyxy: list[int]
    expanded_box_xyxy: list[int]


def clamp(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, round(value))))


def bbox_to_xyxy(points: Iterable[Iterable[float]], width: int, height: int) -> list[int]:
    xs = []
    ys = []
    for point in points:
        x, y = point
        xs.append(float(x))
        ys.append(float(y))
    return [
        clamp(min(xs), 0, width),
        clamp(min(ys), 0, height),
        clamp(max(xs), 0, width),
        clamp(max(ys), 0, height),
    ]


def expand_box(box_xyxy: list[int], width: int, height: int, padding: float) -> list[int]:
    x1, y1, x2, y2 = [float(value) for value in box_xyxy]
    box_width = x2 - x1
    box_height = y2 - y1
    return [
        clamp(x1 - box_width * padding, 0, width),
        clamp(y1 - box_height * padding, 0, height),
        clamp(x2 + box_width * padding, 0, width),
        clamp(y2 + box_height * padding, 0, height),
    ]


def get_reader():
    global _READER
    if easyocr is None:
        raise RuntimeError("easyocr no esta instalado")
    if _READER is None:
        _READER = easyocr.Reader(["es", "en"], gpu=False, verbose=False)
    return _READER


def detect_regex_matches(
    image: Image.Image,
    rules: Sequence[dict],
    padding: float,
    min_confidence: float = 0.20,
) -> list[OCRDetection]:
    active_rules = [rule for rule in rules if rule.get("enabled")]
    if not active_rules:
        return []

    compiled_rules = [
        (str(rule.get("id", "")), str(rule["name"]), re.compile(str(rule["pattern"]), re.IGNORECASE))
        for rule in active_rules
    ]
    reader = get_reader()
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    detections: list[OCRDetection] = []

    for points, text, confidence in reader.readtext(np.asarray(rgb_image), detail=1, paragraph=False):
        if float(confidence) < min_confidence:
            continue
        for rule_id, rule_name, pattern in compiled_rules:
            if not pattern.search(str(text)):
                continue
            box = bbox_to_xyxy(points, width=width, height=height)
            detections.append(
                OCRDetection(
                    rule_id=rule_id,
                    rule_name=rule_name,
                    confidence=float(confidence),
                    box_xyxy=box,
                    expanded_box_xyxy=expand_box(box, width=width, height=height, padding=padding),
                )
            )
            break
    return detections


def detections_as_private_dicts(detections: Sequence[OCRDetection]) -> list[dict]:
    return [asdict(detection) for detection in detections]
