"""Layout-preserving OCR with illumination correction for reflective packaging.

Keep competing readings as evidence rather than appending every OCR pass to one
text stream. Coordinates are always in the input image's coordinate system.
"""
import os
import re
from collections import defaultdict

import cv2
import numpy as np


def _read_lines(image, pytesseract, source, scale=1.0, psm=6, min_confidence=45):
    data = pytesseract.image_to_data(
        image, config=f"--oem 3 --psm {psm}",
        output_type=pytesseract.Output.DICT,
        timeout=float(os.environ.get("OCR_PASS_TIMEOUT", "45")),
    )
    groups = defaultdict(list)
    for i, word in enumerate(data["text"]):
        if word.strip():
            # line_num alone repeats in different blocks and paragraphs.
            key = tuple(data[k][i] for k in ("block_num", "par_num", "line_num"))
            groups[key].append(i)
    lines = []
    for ids in groups.values():
        words = []
        for i in ids:
            word = data["text"][i].strip()
            confidence = float(data["conf"][i])
            if not re.search(r"[\w℞]", word):
                continue
            words.append({"text": word, "confidence": confidence,
                          "left": data["left"][i] / scale,
                          "top": data["top"][i] / scale,
                          "width": data["width"][i] / scale,
                          "height": data["height"][i] / scale})
        if not words:
            continue
        confidence = sum(w["confidence"] * len(w["text"]) for w in words) / sum(len(w["text"]) for w in words)
        text = " ".join(w["text"] for w in words)
        is_rx = bool(re.fullmatch(r"(?:N\s*Rx|X\s*Rx|R\s*x|℞)", text, re.I))
        if confidence < min_confidence or (len(re.sub(r"[^A-Za-z0-9]", "", text)) < 5 and not is_rx):
            continue
        x = min(w["left"] for w in words)
        y = min(w["top"] for w in words)
        right = max(w["left"] + w["width"] for w in words)
        bottom = max(w["top"] + w["height"] for w in words)
        lines.append({"text": " ".join(w["text"] for w in words),
                      "confidence": round(confidence, 1), "source": source,
                      "box": [x, y, right - x, bottom - y], "words": words})
    return lines


def _same_line(a, b):
    x, y, w, h = a["box"]
    xx, yy, ww, hh = b["box"]
    overlap_y = max(0, min(y + h, yy + hh) - max(y, yy))
    overlap_x = max(0, min(x + w, xx + ww) - max(x, xx))
    if a.get('source') == b.get('source') == 'paddle_rotated':
        return overlap_x / max(1,min(w,ww)) > .7 and overlap_y / max(1,min(h,hh)) > .55
    return overlap_y / max(1, min(h, hh)) > 0.55 and overlap_x / max(1, min(w, ww)) > 0.3


def merge_lines(candidates):
    selected = []
    def rank(row):
        anchors = re.findall(r"\b(?:store|licence|license|manufactured|contains|prescription|batch|lot|expiry)\b", row["text"], re.I)
        metric = bool(re.search(r"\b\d+\s*(?:mg|ml|mcg|°C)\b", row["text"], re.I))
        return row["confidence"] + min(12, len(anchors) * 6) + 8 * metric
    for line in sorted(candidates, key=rank, reverse=True):
        existing = next((row for row in selected if _same_line(row, line)), None)
        if existing is None:
            selected.append(dict(line, alternatives=[]))
        elif line["text"] != existing["text"]:
            existing["alternatives"].append({k: line[k] for k in ("text", "confidence", "source")})
    return sorted(selected, key=lambda row: (row["box"][1], row["box"][0]))


def recover_rx_symbol(img, lines, pytesseract):
    """Re-read isolated header glyphs misrecognized as IX, with visual checks.

    A stylized Rx often connects the R leg to the small x. Require one dominant
    connected glyph and an independent R reading; never replace IX in body text.
    """
    h, w = img.shape[:2]
    for row in lines:
        for word in row["words"]:
            if word["text"].lower() not in ("ix", "ik"):
                continue
            x, y, ww, hh = (word[k] for k in ("left", "top", "width", "height"))
            if y > h * 0.35 or x > w * 0.5 or not 0.35 < ww / max(hh, 1) < 1.5:
                continue
            pad = max(5, int(hh * 0.18))
            left, top = max(0, int(x) - pad), max(0, int(y) - pad)
            crop = img[top:min(h, int(y + hh) + pad), left:min(w, int(x + ww) + pad)]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            _, _, stats, _ = cv2.connectedComponentsWithStats(binary)
            substantial = [s for s in stats[1:] if s[4] > ww * hh * 0.025]
            if len(substantial) != 1:
                continue
            try:
                reading = pytesseract.image_to_string(gray, config="--oem 3 --psm 8", timeout=15).strip()
            except RuntimeError:
                continue
            if reading.lower() not in ("r", "re", "rx", "℞"):
                continue
            row["alternatives"].append({k: row[k] for k in ("text", "confidence", "source")})
            row["text"] = re.sub(r"(?<!\w)" + re.escape(word["text"]) + r"(?!\w)", "Rx", row["text"], count=1)
            word["text"] = "Rx"
            row["source"] += "+rx_glyph_crop"
            return


def extract_lines(img, pytesseract):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    # Mask QR modules before OCR: otherwise they become spurious words attached
    # to lot/date lines. This copy does not affect barcode detection.
    try:
        factor = min(1.0, 1800 / max(h, w))
        preview = cv2.resize(img, None, fx=factor, fy=factor)
        found, points = cv2.QRCodeDetector().detect(preview)
        if points is not None:
            points = points / factor
        if found and points is not None:
            mask = np.zeros_like(gray)
            cv2.fillConvexPoly(mask, points.reshape(-1, 2).astype(np.int32), 255)
            mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))
            img = img.copy()
            img[mask > 0] = 255
            gray[mask > 0] = 255
    except cv2.error:
        pass

    candidates, errors = [], []
    channels = [("normalized_gray", gray)]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    red = ((hsv[:, :, 0] < 13) | (hsv[:, :, 0] > 167)) & (hsv[:, :, 1] > 60)
    if np.mean(red) > 0.005:
        # The red channel lightens a red warning panel while preserving black ink.
        channels.append(("normalized_red", img[:, :, 2]))
    for source, channel in channels:
        background = cv2.GaussianBlur(channel, (0, 0), max(h, w) / 120)
        smooth = cv2.GaussianBlur(channel, (3, 3), 0)
        normalized = cv2.divide(smooth, np.maximum(background, 1), scale=255)
        binary = cv2.threshold(normalized, 180, 255, cv2.THRESH_BINARY)[1]
        try:
            candidates.extend(_read_lines(binary, pytesseract, source))
        except RuntimeError as exc:
            errors.append(f"{source}: {exc}")

    # A second scale helps broken characters reconnect without sacrificing the
    # original-resolution readings of identifiers and small print.
    scale = min(1.0, 3000 / max(h, w))
    if scale < 0.9:
        small = cv2.resize(gray, None, fx=scale, fy=scale)
        background = cv2.GaussianBlur(small, (0, 0), max(small.shape) / 120)
        normalized = cv2.divide(cv2.GaussianBlur(small, (3, 3), 0), np.maximum(background, 1), scale=255)
        binary = cv2.threshold(normalized, 180, 255, cv2.THRESH_BINARY)[1]
        try:
            candidates.extend(_read_lines(binary, pytesseract, "normalized_small", scale))
        except RuntimeError as exc:
            errors.append(f"normalized_small: {exc}")

    # A grayscale pass preserves thin print removed by strong thresholding.
    scale = min(1.0, 3000 / max(h, w))
    plain = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
    try:
        candidates.extend(_read_lines(cv2.medianBlur(plain, 3), pytesseract, "gray", scale))
    except RuntimeError as exc:
        errors.append(f"gray: {exc}")
    try:
        enhanced = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(plain)
        for line in _read_lines(enhanced, pytesseract, "sparse", scale, psm=11):
            # Sparse OCR is useful for isolated small print, but its tiny high-
            # confidence fragments must not replace complete paragraph lines.
            is_rx = bool(re.fullmatch(r"(?:N\s*Rx|X\s*Rx|R\s*x|℞)", line["text"], re.I))
            if line["confidence"] >= 65 and (len(line["text"]) >= 12 or is_rx) and not any(_same_line(line, row) for row in candidates):
                candidates.append(line)
    except RuntimeError as exc:
        errors.append(f"sparse: {exc}")
    if not candidates and errors:
        raise RuntimeError("All OCR passes failed: " + "; ".join(errors))
    selected = merge_lines(candidates)
    # Re-read identifiers in tight, automatically located word crops. Whole-page
    # segmentation can confuse a leading C with a copyright symbol on foil.
    for row in selected:
        if not re.search(r"\b(?:lot|batch|b\.?no|licen[cs]e|lic\.)\b", row["text"], re.I):
            continue
        for word in row["words"]:
            if not re.fullmatch(r"[\w©/-]*\d[\w©/-]{3,}", word["text"]):
                continue
            margin = max(5, int(word["height"] * 0.35))
            x, y = max(0, int(word["left"]) - margin), max(0, int(word["top"]) - margin)
            right = min(w, int(word["left"] + word["width"]) + margin)
            bottom = min(h, int(word["top"] + word["height"]) + margin)
            try:
                readings = _read_lines(gray[y:bottom, x:right], pytesseract, "identifier_crop", psm=7, min_confidence=0)
            except RuntimeError:
                continue
            if not readings:
                continue
            reading = max(readings, key=lambda r: r["confidence"])
            token = reading["text"].strip()
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/-]{3,30}", token):
                continue
            invalid_original = not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/-]{3,30}", word["text"])
            if token != word["text"] and (invalid_original or reading["confidence"] >= word["confidence"]):
                row["alternatives"].append({k: row[k] for k in ("text", "confidence", "source")})
                row["text"] = row["text"].replace(word["text"], token, 1)
                row["source"] += "+identifier_crop"
                word["text"] = token
                word["confidence"] = reading["confidence"]
    recover_rx_symbol(img, selected, pytesseract)
    return selected, errors
