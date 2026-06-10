#!/usr/bin/env python3
"""Radiograph anonymization pipeline using a trained YOLO model.

The local application uses `blur_then_black`: blur is applied only as an
intermediate step, then the detected pixels are overwritten with black so the
final PNG does not contain recoverable text in those regions.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from ultralytics import YOLO

from ocr_redaction import detect_regex_matches, detections_as_private_dicts
from ocr_rules import DEFAULT_RULES_PATH, load_ocr_rules

try:
    import pydicom
    from pydicom.pixel_data_handlers.util import apply_voi_lut
except Exception:
    pydicom = None
    apply_voi_lut = None


REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "Application"
MODEL_ROOT = REPO_ROOT / "Model"
DEFAULT_MODEL = MODEL_ROOT / "runs" / "radiograph_phi_detection" / "augmented" / "weights" / "best.pt"
REDACTION_METHOD = "blur_then_black"
DEFAULT_CLASS_NAMES = ("name", "id", "age", "date", "time")
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".dcm", ".dicom"}
SUPPORTED_INPUT_SUFFIXES = SUPPORTED_IMAGE_SUFFIXES | {".zip"}


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    box_xyxy: list[int]
    expanded_box_xyxy: list[int]


@dataclass
class PreparedInput:
    original_path: Path
    inference_path: Path
    display_name: str
    output_stem: str
    source_type: str


@dataclass
class SkippedInput:
    path: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Detect sensitive text boxes in radiographs and irreversibly "
            "redact them using a trained YOLO model."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Input image, ZIP or directory.")
    parser.add_argument("--output", required=True, type=Path, help="Output PNG file or output directory.")
    parser.add_argument("--model", default=DEFAULT_MODEL, type=Path, help=f"YOLO .pt model path. Default: {DEFAULT_MODEL}")
    parser.add_argument("--conf", default=0.25, type=float, help="YOLO confidence threshold.")
    parser.add_argument(
        "--fields",
        default=",".join(DEFAULT_CLASS_NAMES),
        help=(
            "Comma-separated YOLO fields to redact. "
            f"Default: {','.join(DEFAULT_CLASS_NAMES)}"
        ),
    )
    parser.add_argument(
        "--padding",
        default=0.10,
        type=float,
        help="Relative expansion applied to each detected box before redaction. Example: 0.10 expands 10%%.",
    )
    parser.add_argument("--save-preview", action="store_true", help="Save preview images with detected boxes drawn.")
    parser.add_argument("--no-json", action="store_true", help="Do not save JSON metadata or batch summaries.")
    parser.add_argument(
        "--ocr-rules",
        default=DEFAULT_RULES_PATH,
        type=Path,
        help=f"OCR regex rules JSON path. Default: {DEFAULT_RULES_PATH}",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Optional Ultralytics device, e.g. cpu, mps, 0. If omitted, Ultralytics chooses automatically.",
    )
    return parser.parse_args()


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES


def is_supported_input(path: Path) -> bool:
    return path.is_dir() or path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES


def parse_selected_class_names(raw_fields: str | Sequence[str] | None) -> set[str] | None:
    if raw_fields is None:
        return None
    if isinstance(raw_fields, str):
        fields = [field.strip().lower() for field in raw_fields.split(",")]
    else:
        fields = [str(field).strip().lower() for field in raw_fields]
    selected = {field for field in fields if field}
    invalid = selected.difference(DEFAULT_CLASS_NAMES)
    if invalid:
        raise ValueError(f"Campos no validos: {', '.join(sorted(invalid))}")
    if not selected:
        raise ValueError("Selecciona al menos un campo para anonimizar")
    return selected


def sanitize_text(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value)


def safe_stem(path: Path) -> str:
    parts = [part for part in path.with_suffix("").parts if part not in ("", ".", "..")]
    stem = "_".join(parts[-3:]) if len(parts) > 1 else path.stem
    return sanitize_text(stem)


def relative_to_or_none(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def iter_input_images(input_path: Path) -> list[Path]:
    prepared, skipped, temp_dir = prepare_inputs([input_path])
    if temp_dir is not None:
        temp_dir.cleanup()
    if not prepared:
        reason = skipped[0].reason if skipped else f"No supported images found in: {input_path}"
        raise ValueError(reason)
    return [item.inference_path for item in prepared]


def collect_input_files(paths: Sequence[Path], extraction_root: Path) -> tuple[list[Path], list[SkippedInput]]:
    files: list[Path] = []
    skipped: list[SkippedInput] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            skipped.append(SkippedInput(str(path), "No existe"))
            continue
        if path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                if child.suffix.lower() in SUPPORTED_INPUT_SUFFIXES:
                    files.append(child)
                else:
                    skipped.append(SkippedInput(str(child), "Formato no soportado"))
            continue
        if path.suffix.lower() == ".zip":
            try:
                extracted, zip_skipped = extract_zip(path, extraction_root)
                files.extend(extracted)
                skipped.extend(zip_skipped)
            except Exception as exc:
                skipped.append(SkippedInput(str(path), f"ZIP no legible: {exc}"))
            continue
        if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
            files.append(path)
        else:
            skipped.append(SkippedInput(str(path), "Formato no soportado"))
    return files, skipped


def extract_zip(zip_path: Path, extraction_root: Path) -> tuple[list[Path], list[SkippedInput]]:
    extracted_files: list[Path] = []
    skipped: list[SkippedInput] = []
    target_root = extraction_root / sanitize_text(zip_path.stem)
    target_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_path = Path(member.filename)
            if member_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
                skipped.append(SkippedInput(f"{zip_path}!{member.filename}", "Formato no soportado en ZIP"))
                continue
            safe_parts = [part for part in member_path.parts if part not in ("", ".", "..")]
            if not safe_parts:
                skipped.append(SkippedInput(f"{zip_path}!{member.filename}", "Ruta no valida en ZIP"))
                continue
            target_path = target_root.joinpath(*safe_parts)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target_path.open("wb") as target:
                target.write(source.read())
            extracted_files.append(target_path)
    return extracted_files, skipped


def load_standard_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def load_dicom_image(path: Path) -> Image.Image:
    if pydicom is None:
        raise RuntimeError("pydicom no esta instalado")
    dataset = pydicom.dcmread(str(path))
    array = dataset.pixel_array
    if apply_voi_lut is not None:
        try:
            array = apply_voi_lut(array, dataset)
        except Exception:
            pass
    array = np.asarray(array, dtype=np.float32)
    if array.ndim == 3 and array.shape[-1] in (3, 4):
        return Image.fromarray(array.clip(0, 255).astype(np.uint8)).convert("RGB")
    if array.ndim > 2:
        array = array[0]
    if getattr(dataset, "PhotometricInterpretation", "") == "MONOCHROME1":
        array = np.max(array) - array
    low = float(np.nanmin(array))
    high = float(np.nanmax(array))
    if high <= low:
        normalized = np.zeros(array.shape, dtype=np.uint8)
    else:
        normalized = ((array - low) / (high - low) * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(normalized).convert("RGB")


def load_input_image(path: Path) -> Image.Image:
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        return load_standard_image(path)
    if suffix in {".dcm", ".dicom"}:
        return load_dicom_image(path)
    raise ValueError("Formato no soportado")


def prepare_inputs(paths: Sequence[Path], temp_dir: tempfile.TemporaryDirectory | None = None) -> tuple[list[PreparedInput], list[SkippedInput], tempfile.TemporaryDirectory | None]:
    owned_temp_dir = temp_dir is None
    temp_dir = temp_dir or tempfile.TemporaryDirectory(prefix="radiograph_inputs_")
    temp_root = Path(temp_dir.name)
    extraction_root = temp_root / "extracted"
    converted_root = temp_root / "converted"
    converted_root.mkdir(parents=True, exist_ok=True)

    files, skipped = collect_input_files(paths, extraction_root)
    prepared: list[PreparedInput] = []
    used_stems: set[str] = set()
    for path in files:
        try:
            image = load_input_image(path)
            extracted_relative_path = relative_to_or_none(path, extraction_root)
            if extracted_relative_path is not None:
                stem = safe_stem(extracted_relative_path)
            else:
                stem = safe_stem(path)
            if stem in used_stems:
                stem = f"{stem}_{len(used_stems)}"
            used_stems.add(stem)
            inference_path = converted_root / f"{stem}.png"
            image.save(inference_path, format="PNG")
            prepared.append(
                PreparedInput(
                    original_path=path,
                    inference_path=inference_path,
                    display_name=str(path),
                    output_stem=stem,
                    source_type=path.suffix.lower().lstrip("."),
                )
            )
        except Exception as exc:
            skipped.append(SkippedInput(str(path), f"No se pudo leer como imagen: {exc}"))
    if owned_temp_dir:
        return prepared, skipped, temp_dir
    return prepared, skipped, None


def output_path_for(input_image: Path, input_root: Path, output: Path) -> Path:
    if input_root.is_file():
        if output.suffix.lower() == ".png":
            return output
        return output / f"{input_image.stem}_anonymized.png"
    return output / f"{input_image.stem}_anonymized.png"


def output_path_for_selection(input_image: Path, output: Path) -> Path:
    return output / f"{input_image.stem}_anonymized.png"


def output_path_for_prepared(item: PreparedInput, output: Path) -> Path:
    return output / f"{item.output_stem}_anonymized.png"


def clamp(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, round(value))))


def expand_box(box_xyxy: Iterable[float], width: int, height: int, padding: float) -> list[int]:
    x1, y1, x2, y2 = [float(value) for value in box_xyxy]
    box_width = x2 - x1
    box_height = y2 - y1
    pad_x = box_width * padding
    pad_y = box_height * padding
    return [
        clamp(x1 - pad_x, 0, width),
        clamp(y1 - pad_y, 0, height),
        clamp(x2 + pad_x, 0, width),
        clamp(y2 + pad_y, 0, height),
    ]


def apply_redaction(image_array: np.ndarray, box: list[int]) -> None:
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return

    region = image_array[y1:y2, x1:x2]
    # Blur is performed only as an intermediate step; final pixels are overwritten.
    pil_region = Image.fromarray(region).filter(ImageFilter.GaussianBlur(radius=8))
    region[:] = np.asarray(pil_region, dtype=np.uint8)
    region[:] = 0


def draw_preview(original_image: Image.Image, detections: list[Detection]) -> Image.Image:
    preview = original_image.copy()
    draw = ImageDraw.Draw(preview)
    for detection in detections:
        x1, y1, x2, y2 = detection.expanded_box_xyxy
        label = f"{detection.class_name} {detection.confidence:.2f}"
        draw.rectangle((x1, y1, x2, y2), outline="red", width=2)
        text_y = max(0, y1 - 12)
        draw.text((x1, text_y), label, fill="red")
    return preview


def detections_from_result(
    result,
    width: int,
    height: int,
    padding: float,
    selected_class_names: set[str] | None = None,
) -> list[Detection]:
    detections: list[Detection] = []
    names = result.names
    boxes = result.boxes
    if boxes is None:
        return detections

    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    class_ids = boxes.cls.cpu().numpy().astype(int)

    for box, confidence, class_id in zip(xyxy, confs, class_ids):
        class_name = str(names.get(int(class_id), f"class_{class_id}"))
        if selected_class_names is not None and class_name.lower() not in selected_class_names:
            continue
        box_int = [clamp(box[0], 0, width), clamp(box[1], 0, height), clamp(box[2], 0, width), clamp(box[3], 0, height)]
        expanded = expand_box(box, width=width, height=height, padding=padding)
        detections.append(
            Detection(
                class_id=int(class_id),
                class_name=class_name,
                confidence=float(confidence),
                box_xyxy=box_int,
                expanded_box_xyxy=expanded,
            )
        )
    return detections


def anonymize_image(
    model: YOLO,
    input_image: Path,
    output_image: Path,
    conf: float,
    padding: float,
    save_preview: bool,
    device: str | None,
    write_metadata: bool = True,
    selected_class_names: set[str] | None = None,
    ocr_rules: Sequence[dict] | None = None,
) -> dict:
    original = Image.open(input_image).convert("RGB")
    width, height = original.size

    predict_kwargs = {"source": str(input_image), "conf": conf, "verbose": False}
    if device:
        predict_kwargs["device"] = device
    result = model.predict(**predict_kwargs)[0]
    detections = detections_from_result(
        result,
        width=width,
        height=height,
        padding=padding,
        selected_class_names=selected_class_names,
    )

    ocr_detections = detect_regex_matches(original, rules=ocr_rules or [], padding=padding)

    redacted = np.asarray(original.copy(), dtype=np.uint8).copy()
    for detection in detections:
        apply_redaction(redacted, detection.expanded_box_xyxy)
    for detection in ocr_detections:
        apply_redaction(redacted, detection.expanded_box_xyxy)

    output_image.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(redacted).save(output_image, format="PNG")

    metadata = {
        "input": str(input_image),
        "output": str(output_image),
        "method": REDACTION_METHOD,
        "confidence_threshold": conf,
        "padding": padding,
        "selected_fields": sorted(selected_class_names) if selected_class_names is not None else list(DEFAULT_CLASS_NAMES),
        "detections": [asdict(detection) for detection in detections],
        "ocr_matches": detections_as_private_dicts(ocr_detections),
    }
    json_path = output_image.with_suffix(".json")
    if write_metadata:
        json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if save_preview and write_metadata:
        preview_dir = output_image.parent / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / f"{output_image.stem}_preview.png"
        draw_preview(original, detections).save(preview_path, format="PNG")
        metadata["preview"] = str(preview_path)
        json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return metadata


def anonymize_prepared_image(
    model: YOLO,
    prepared_input: PreparedInput,
    output_image: Path,
    conf: float,
    padding: float,
    save_preview: bool,
    device: str | None,
    write_metadata: bool = True,
    selected_class_names: set[str] | None = None,
    ocr_rules: Sequence[dict] | None = None,
) -> dict:
    summary = anonymize_image(
        model=model,
        input_image=prepared_input.inference_path,
        output_image=output_image,
        conf=conf,
        padding=padding,
        save_preview=save_preview,
        device=device,
        write_metadata=write_metadata,
        selected_class_names=selected_class_names,
        ocr_rules=ocr_rules,
    )
    summary["input"] = prepared_input.display_name
    summary["source_type"] = prepared_input.source_type
    return summary


def process_images(
    input_path: Path,
    output_path: Path,
    model_path: Path = DEFAULT_MODEL,
    conf: float = 0.25,
    padding: float = 0.10,
    save_preview: bool = False,
    device: str | None = None,
    write_metadata: bool = False,
    selected_class_names: str | Sequence[str] | None = None,
    ocr_rules: Sequence[dict] | None = None,
    progress_callback=None,
) -> dict:
    return process_image_selection(
        image_paths=[input_path],
        output_path=output_path,
        model_path=model_path,
        conf=conf,
        padding=padding,
        save_preview=save_preview,
        device=device,
        write_metadata=write_metadata,
        selected_class_names=selected_class_names,
        ocr_rules=ocr_rules,
        progress_callback=progress_callback,
    )


def process_image_selection(
    image_paths: Sequence[Path],
    output_path: Path,
    model_path: Path = DEFAULT_MODEL,
    conf: float = 0.25,
    padding: float = 0.10,
    save_preview: bool = False,
    device: str | None = None,
    write_metadata: bool = False,
    selected_class_names: str | Sequence[str] | None = None,
    ocr_rules: Sequence[dict] | None = None,
    progress_callback=None,
) -> dict:
    model_path = model_path.resolve()
    output_path = output_path.resolve()
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if padding < 0:
        raise ValueError("padding must be >= 0")
    selected_classes = parse_selected_class_names(selected_class_names)
    active_ocr_rules = [rule for rule in (ocr_rules or []) if rule.get("enabled")]

    temp_dir = tempfile.TemporaryDirectory(prefix="radiograph_prepare_")
    prepared_inputs, skipped, _ = prepare_inputs(image_paths, temp_dir=temp_dir)
    if not prepared_inputs:
        temp_dir.cleanup()
        return {"processed": [], "skipped": [asdict(item) for item in skipped]}

    output_path.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(model_path))
    summaries = []
    total = len(prepared_inputs)
    for index, prepared_input in enumerate(prepared_inputs, start=1):
        target_path = output_path_for_prepared(prepared_input, output_path)
        summary = anonymize_prepared_image(
            model=model,
            prepared_input=prepared_input,
            output_image=target_path,
            conf=conf,
            padding=padding,
            save_preview=save_preview,
            device=device,
            write_metadata=write_metadata,
            selected_class_names=selected_classes,
            ocr_rules=active_ocr_rules,
        )
        summaries.append(summary)
        if progress_callback:
            progress_callback(index, total, prepared_input.original_path, summary)

    if write_metadata and len(summaries) > 1:
        batch_summary = output_path / "batch_summary.json"
        batch_summary.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    temp_dir.cleanup()
    return {"processed": summaries, "skipped": [asdict(item) for item in skipped]}


def main() -> None:
    args = parse_args()
    ocr_rules = load_ocr_rules(args.ocr_rules)
    result = process_images(
        input_path=args.input,
        output_path=args.output,
        model_path=args.model,
        conf=args.conf,
        padding=args.padding,
        save_preview=args.save_preview,
        device=args.device,
        write_metadata=not args.no_json,
        selected_class_names=args.fields,
        ocr_rules=ocr_rules,
        progress_callback=lambda index, total, image_path, summary: print(
            f"[{index}/{total}] Saved {summary['output']} "
            f"({len(summary['detections']) + len(summary['ocr_matches'])} redactions)"
        ),
    )
    summaries = result["processed"]
    skipped = result["skipped"]
    for item in skipped:
        print(f"Skipped {item['path']}: {item['reason']}")
    if len(summaries) > 1 and not args.no_json:
        print(f"Saved {Path(args.output).resolve() / 'batch_summary.json'}")


if __name__ == "__main__":
    main()
