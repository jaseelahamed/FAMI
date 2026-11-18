"""
Deep OCR pass for hard images (photos of foil blister packs, tiny text).

Why it exists
-------------
Tesseract's normal full-page mode fails on embossed foil: the diamond texture is
read as gibberish (and is very slow to process), so the real text is lost.
Reading the image in narrow pieces works far better, because each piece is
normalised on its own and the foil texture is suppressed with a median filter:

  * Horizontal bands  - full-width bands read as paragraphs (--psm 6), with a
                        gray and a green-channel variant (the green channel helps
                        with text on red/coloured panels).
  * Vertical strips   - the image is cut into tall strips and rotated both ways, to
                        read sideways text such as vertical "B.No. / Mfg / Exp"
                        print on blister foils.

It only supplies extra OCR *text*. The validation rules are unchanged, so it
cannot loosen what counts as a pass.

Environment variables
---------------------
OCR_DEEP_PASS=0        disable the deep pass
OCR_DEEP_BUDGET=<sec>  time limit (default 40)
"""

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

# Words that typically appear on a medicine label. If the fast OCR already found
# enough of them, the deep pass is skipped (keeps clean images fast).
LABEL_KEYWORDS = (
    "tablet", "capsule", "syrup", "injection", "contains", "each", "mfg", "mfd",
    "lic", "batch", "b.no", "exp", "manufactured", "marketed", "store", "storage",
    "protect", "light", "moisture", "dosage", "directed", "physician", "schedule",
    "prescription", "caution", "warning", "keep", "reach", "children", "mg", "ml",
    "pharma", "laborator", "limited", "ltd", "pvt", "address", "india",
)
MIN_KEYWORD_HITS = 6


def keyword_hits(text: str) -> int:
    """Number of distinct label keywords present in the text (OCR quality signal)."""
    low = text.lower()
    return sum(1 for k in LABEL_KEYWORDS if k in low)


def needs_deep_pass(text: str) -> bool:
    if os.environ.get("OCR_DEEP_PASS", "1") == "0":
        return False
    return keyword_hits(text) < MIN_KEYWORD_HITS


def clean_lines(raw: str):
    """Drops junk tokens (stray symbols) but keeps the readable words on each line."""
    keep_symbols = {"&", "+", "-", ":", "/"}
    lines = []
    for line in raw.splitlines():
        tokens = []
        for tok in line.split():
            alnum = sum(c.isalnum() for c in tok)
            if tok in keep_symbols or (alnum >= 2 and alnum / len(tok) >= 0.6):
                tokens.append(tok)
        cleaned = " ".join(tokens).strip()
        if len(cleaned) >= 4 and re.search(r"[A-Za-z]{3,}", cleaned):
            lines.append(cleaned)
    return lines


def _prep(crop, scale, mode, ksize=3):
    """Median-filtered, contrast-stretched single channel (suppresses foil texture)."""
    if mode == "green":
        g = crop[:, :, 1]
    else:
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if scale != 1.0:
        g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return cv2.normalize(cv2.medianBlur(g, ksize), None, 0, 255, cv2.NORM_MINMAX)


def deep_ocr_lines(img, pytesseract):
    """Returns a list of recovered text lines for a BGR image."""
    h, w = img.shape[:2]
    deadline = time.time() + float(os.environ.get("OCR_DEEP_BUDGET", "20"))
    workers = max(1, min(4, os.cpu_count() or 1))

    jobs = []  # (crop, scale, mode)

    # Horizontal bands (full width), overlapping so no line is cut in half
    band = max(120, int(h * 0.22))
    step = max(60, int(band * 0.6))
    ys = list(range(0, max(h - band, 0) + 1, step))
    if ys[-1] + band < h:
        ys.append(max(h - band, 0))
    for y in ys:
        crop = img[y:y + band, :]
        scale = 1.5 if max(crop.shape[:2]) < 1100 else 1.0
        for mode in ("gray", "green"):
            jobs.append((crop, scale, mode))

    # Vertical strips, rotated both ways, for sideways text
    strip_w = max(120, int(w * 0.35))
    xs = sorted({min(int(w * f), max(w - strip_w, 0)) for f in (0.0, 0.2, 0.4, 0.6, 0.65)})
    for x in xs:
        strip = img[:, x:x + strip_w]
        for rot in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
            rotated = cv2.rotate(strip, rot)
            scale = 1.5 if max(rotated.shape[:2]) < 900 else 1.0
            jobs.append((rotated, scale, "gray"))

    # Narrow, enlarged strips: small sideways print (e.g. "Mfg. Lic. No.") needs a
    # bigger scale than the wide strips above provide.
    narrow_w = max(100, int(w * 0.22))
    for f in (0.50, 0.58, 0.66):
        x = min(int(w * f), max(w - narrow_w, 0))
        rotated = cv2.rotate(img[:, x:x + narrow_w], cv2.ROTATE_90_CLOCKWISE)
        jobs.append((rotated, 2.0, "gray"))

    def run(job):
        if time.time() > deadline:
            return ""
        crop, scale, mode = job
        try:
            return pytesseract.image_to_string(
                _prep(crop, scale, mode), config='--oem 3 --psm 6', timeout=30)
        except Exception:
            return ""

    lines = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for raw in pool.map(run, jobs):
            lines.extend(clean_lines(raw))
    return lines
