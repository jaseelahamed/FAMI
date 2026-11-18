"""
Prints exactly what the OCR reads from an image and how each of the 14 checks
turns out. Useful for finding out why a field shows "Not Detected" on one machine
but not another.

Usage:
    python debug_ocr.py                 # scans the built-in demo label
    python debug_ocr.py my_label.jpg    # scans your own image

Output is also saved to ocr_debug.txt so it can be shared.
"""

import os
import sys
import tempfile
import json
from app import MedicineLabelValidator, configure_tesseract, generate_sample_medicine_label


def main():
    configure_tesseract()
    try:
        import pytesseract
        version = str(pytesseract.get_tesseract_version())
    except Exception as exc:  # pragma: no cover
        version = f"unknown ({exc})"

    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = os.path.join(tempfile.gettempdir(), "debug_demo_label.png")
        generate_sample_medicine_label(path)

    validator = MedicineLabelValidator(path)
    report = validator.run_full_pipeline()
    checks = report["regulatory_validation"]["field_checks"]

    out = []
    out.append(f"OCR engine used: {validator.ocr_engine}")
    out.append(f"Tesseract fallback version: {version}")
    out.append(f"Image: {path}")
    out.append("")
    out.append("===== FULL OCR TEXT (repr, so hidden characters are visible) =====")
    for line in validator.extracted_text.splitlines():
        out.append(repr(line))
    out.append("")
    out.append("===== CHECKS =====")
    for name, info in checks.items():
        out.append(f"{info['status']:20s} {name}: {info['extracted_value'][:90]}")
        for note in info.get("review_notes", []):
            out.append(f"  Review: {note}")
    out.append("")
    out.append(f"SCORE: {report['regulatory_validation']['score_percentage']}%")
    out.append(f"VERDICT: {report['regulatory_validation']['overall_status']}")

    text = "\n".join(out)
    print(text)
    with open("ocr_debug.txt", "w", encoding="utf-8") as fh:
        fh.write(text)
    print("\n(saved to ocr_debug.txt)")
    with open("ocr_debug.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print("(full report, line confidence and alternative readings saved to ocr_debug.json)")


if __name__ == "__main__":
    main()

