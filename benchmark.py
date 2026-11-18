"""
Scan-time benchmark for the label validator.

Usage:
    python benchmark.py                      # uses a generated demo label
    python benchmark.py img1.jpg img2.png    # uses your own images

Compare settings by running it with different environment variables, e.g.:
    OCR_MAX_DIM=900 python benchmark.py img1.jpg
    OCR_ROTATION_PASSES=0 python benchmark.py img1.jpg
"""

import os
import sys
import time
import tempfile

from app import MedicineLabelValidator, configure_tesseract, generate_sample_medicine_label


def time_scan(path: str) -> float:
    start = time.perf_counter()
    validator = MedicineLabelValidator(path)
    report = validator.run_full_pipeline()
    out = os.path.join(tempfile.gettempdir(), "bench_annotated.jpg")
    validator.generate_annotated_output(out)
    elapsed = time.perf_counter() - start
    score = report["regulatory_validation"]["score_percentage"]
    print(f"{os.path.basename(path):30s} {elapsed:6.2f}s   score={score}%")
    return elapsed


def main():
    configure_tesseract()
    print(f"OCR_MAX_DIM={os.environ.get('OCR_MAX_DIM', '1200')}  "
          f"OCR_ROTATION_PASSES={os.environ.get('OCR_ROTATION_PASSES', '1')}\n")

    images = sys.argv[1:]
    if not images:
        sample = os.path.join(tempfile.gettempdir(), "bench_sample.png")
        generate_sample_medicine_label(sample)
        images = [sample]

    times = [time_scan(p) for p in images]
    print(f"\nAverage: {sum(times) / len(times):.2f}s over {len(times)} image(s)")


if __name__ == "__main__":
    main()

