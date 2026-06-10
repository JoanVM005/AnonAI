#!/usr/bin/env python3
"""Create synthetic DICOM PHI test images from MIDRC-RICORD samples.

The generated files are intended for local pipeline testing only. They keep the
radiograph pixels from the selected MIDRC-RICORD DICOMs, burn fake visible PHI
text into the image area, and update a few DICOM header fields with matching
synthetic values.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image, ImageDraw, ImageFont
from pydicom.uid import ExplicitVRLittleEndian, generate_uid


REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = REPO_ROOT / "Application" / "test"
OUTPUT_DIR = TEST_ROOT / "dicom_phi"

SOURCE_DICOMS = [
    REPO_ROOT
    / "Application"
    / "test"
    / "MIDRC-RICORD-1c-manifest-Jan-2021"
    / "midrc_ricord_1c"
    / "MIDRC-RICORD-1C-419639-002724"
    / "03387"
    / "77899"
    / "68e2f84b-6be6-470f-9376-8d668731806e.dcm",
    REPO_ROOT
    / "Application"
    / "test"
    / "MIDRC-RICORD-1c-manifest-Jan-2021"
    / "midrc_ricord_1c"
    / "MIDRC-RICORD-1C-SITE2-000105"
    / "65881"
    / "17480"
    / "6217b20a-393c-4d25-9560-247d1814449c.dcm",
    REPO_ROOT
    / "Application"
    / "test"
    / "MIDRC-RICORD-1c-manifest-Jan-2021"
    / "midrc_ricord_1c"
    / "MIDRC-RICORD-1C-419639-001155"
    / "71955"
    / "55833"
    / "d6097f4b-b217-4160-8a69-39141de00b02.dcm",
    REPO_ROOT
    / "Application"
    / "test"
    / "MIDRC-RICORD-1c-manifest-Jan-2021"
    / "midrc_ricord_1c"
    / "MIDRC-RICORD-1C-SITE2-000102"
    / "72341"
    / "00526"
    / "32d933ba-b23b-4f68-9e6d-2038932e7407.dcm",
    REPO_ROOT
    / "Application"
    / "test"
    / "MIDRC-RICORD-1c-manifest-Jan-2021"
    / "midrc_ricord_1c"
    / "MIDRC-RICORD-1C-SITE2-000102"
    / "72341"
    / "04568"
    / "6a524629-834a-402f-b7a2-967815b86af7.dcm",
]

SYNTHETIC_CASES = [
    {
        "patient_name": "JANE ORTEGA",
        "patient_id": "93810F",
        "age": "033Y",
        "study_date": "20170208",
        "study_time": "142731",
        "room": "3",
        "accession": "510482",
    },
    {
        "patient_name": "MARC DIAZ",
        "patient_id": "42177A",
        "age": "061Y",
        "study_date": "20190416",
        "study_time": "092214",
        "room": "12",
        "accession": "904155",
    },
    {
        "patient_name": "LUCIA SANTOS",
        "patient_id": "77602K",
        "age": "045Y",
        "study_date": "20201103",
        "study_time": "181955",
        "room": "7",
        "accession": "118370",
    },
    {
        "patient_name": "ADAM RIVERA",
        "patient_id": "56329P",
        "age": "052Y",
        "study_date": "20180621",
        "study_time": "073346",
        "room": "5",
        "accession": "771249",
    },
    {
        "patient_name": "ELENA VEGA",
        "patient_id": "30591M",
        "age": "027Y",
        "study_date": "20210529",
        "study_time": "235008",
        "room": "9",
        "accession": "602844",
    },
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def date_for_overlay(dicom_date: str) -> str:
    if len(dicom_date) != 8:
        return dicom_date
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    month = months[int(dicom_date[4:6]) - 1]
    return f"{dicom_date[6:8]}-{month}-{dicom_date[:4]}"


def time_for_overlay(dicom_time: str) -> str:
    return f"{dicom_time[:2]}:{dicom_time[2:4]}:{dicom_time[4:6]}"


def overlay_masks(shape: tuple[int, int], case: dict[str, str], index: int) -> tuple[Image.Image, Image.Image]:
    height, width = shape
    font_size = max(24, int(min(width, height) * 0.024))
    small_font_size = max(22, int(font_size * 0.82))
    font = load_font(font_size)
    small_font = load_font(small_font_size)
    text = Image.new("L", (width, height), 0)
    background = Image.new("L", (width, height), 0)
    text_draw = ImageDraw.Draw(text)
    background_draw = ImageDraw.Draw(background)

    margin_x = int(width * 0.055)
    margin_y = int(height * 0.035)
    line_gap = int(font_size * 1.12)
    date = date_for_overlay(case["study_date"])
    time = time_for_overlay(case["study_time"])
    name = case["patient_name"]
    patient_id = case["patient_id"]
    age = case["age"].replace("Y", "")

    left_lines = [
        "PORTABLE",
        f"ACC {case['accession']}  ROOM {case['room']}",
    ]
    right_lines = [
        f"{name} ID: {patient_id}  {age}Y",
        f"{date} CHEST  TIME {time}",
    ]
    lower_line = f"AP ERECT  MIDRC TEST {index:02d}"

    left_width = max(text_draw.textbbox((0, 0), line, font=small_font)[2] for line in left_lines)
    left_box = (
        max(0, margin_x - font_size // 2),
        max(0, margin_y - font_size // 3),
        min(width, margin_x + left_width + font_size // 2),
        min(height, margin_y + len(left_lines) * line_gap + font_size // 2),
    )
    background_draw.rectangle(left_box, fill=255)
    for line_no, line in enumerate(left_lines):
        text_draw.text((margin_x, margin_y + line_no * line_gap), line, fill=255, font=small_font)

    right_width = max(text_draw.textbbox((0, 0), line, font=font)[2] for line in right_lines)
    right_x = max(margin_x, width - margin_x - right_width)
    right_box = (
        max(0, right_x - font_size // 2),
        max(0, margin_y - font_size // 3),
        width,
        min(height, margin_y + len(right_lines) * line_gap + font_size // 2),
    )
    background_draw.rectangle(right_box, fill=255)
    for line_no, line in enumerate(right_lines):
        text_draw.text((right_x, margin_y + line_no * line_gap), line, fill=255, font=font)

    if index % 2 == 0:
        lower_width = text_draw.textbbox((0, 0), lower_line, font=small_font)[2]
        lower_y = height - margin_y - line_gap
        lower_box = (
            max(0, margin_x - font_size // 2),
            max(0, lower_y - font_size // 3),
            min(width, margin_x + lower_width + font_size // 2),
            min(height, lower_y + line_gap + font_size // 2),
        )
        background_draw.rectangle(lower_box, fill=255)
        text_draw.text((margin_x, lower_y), lower_line, fill=255, font=small_font)

    return text, background


def burn_text(pixel_array: np.ndarray, case: dict[str, str], index: int, photometric: str) -> np.ndarray:
    array = np.asarray(pixel_array).copy()
    if array.ndim > 2:
        array = array[0]

    text, background = overlay_masks(array.shape, case, index)
    mask = np.asarray(text, dtype=bool)
    background_mask = np.asarray(background, dtype=bool)
    shadow = np.asarray(text, dtype=np.uint8)
    shadow = np.roll(shadow, shift=(max(2, array.shape[0] // 550), max(2, array.shape[1] // 550)), axis=(0, 1)) > 0

    low = int(np.nanmin(array))
    high = int(np.nanmax(array))
    if high <= low:
        high = int(np.iinfo(array.dtype).max)

    white_value = high if photometric != "MONOCHROME1" else low
    shadow_value = low if photometric != "MONOCHROME1" else high
    array[background_mask] = shadow_value
    array[shadow] = shadow_value
    array[mask] = white_value
    return array.astype(pixel_array.dtype, copy=False)


def update_metadata(ds: pydicom.Dataset, case: dict[str, str]) -> None:
    ds.PatientName = case["patient_name"].replace(" ", "^")
    ds.PatientID = case["patient_id"]
    ds.PatientAge = case["age"]
    ds.StudyDate = case["study_date"]
    ds.SeriesDate = case["study_date"]
    ds.AcquisitionDate = case["study_date"]
    ds.ContentDate = case["study_date"]
    ds.StudyTime = case["study_time"]
    ds.SeriesTime = case["study_time"]
    ds.AcquisitionTime = case["study_time"]
    ds.ContentTime = case["study_time"]
    ds.AccessionNumber = case["accession"]
    ds.PatientComments = "Synthetic visible PHI for local test pipeline"
    ds.StudyDescription = "CHEST PORTABLE"
    ds.SeriesDescription = "Synthetic PHI overlay test"
    ds.SOPInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()


def create_test_dicom(source_path: Path, case: dict[str, str], index: int) -> Path:
    ds = pydicom.dcmread(str(source_path))
    if ds.file_meta.TransferSyntaxUID.is_compressed:
        ds.decompress()
    original_pixels = ds.pixel_array
    edited_pixels = burn_text(original_pixels, case, index, getattr(ds, "PhotometricInterpretation", "MONOCHROME2"))

    ds = deepcopy(ds)
    update_metadata(ds, case)
    ds.PixelData = edited_pixels.tobytes()
    ds.Rows, ds.Columns = edited_pixels.shape[:2]
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    output_path = OUTPUT_DIR / f"dicom_phi_test_{index:02d}.dcm"
    ds.save_as(str(output_path), write_like_original=False)
    return output_path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, (source_path, case) in enumerate(zip(SOURCE_DICOMS, SYNTHETIC_CASES), start=1):
        output_path = create_test_dicom(source_path, case, index)
        print(f"[{index}/5] {source_path.name} -> {output_path}")


if __name__ == "__main__":
    main()
