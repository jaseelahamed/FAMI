"""Primary PaddleOCR backend with a Tesseract fallback in app.py.

OCR_ENGINE=paddle (default), tesseract, or auto (legacy Tesseract-first mode).
PADDLE_MODEL=mobile (default) or server explicitly selects PP-OCRv5 models.
PADDLE_MAX_SIDE controls detection resolution (default 2000).
Models download on first use; memory use must be measured for deployment.
"""

import os
import re
from pathlib import Path
import threading

import cv2
import numpy as np

_ENGINE = None
_ENGINE_LOCK = threading.Lock()
_ENGINE_FAILED = False


def available() -> bool:
    try:
        import paddleocr  # noqa: F401
        return True
    except Exception:
        return False


def _get_engine():
    """Creates the PaddleOCR engine once (loading models is slow)."""
    global _ENGINE, _ENGINE_FAILED
    if _ENGINE is not None or _ENGINE_FAILED:
        return _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None or _ENGINE_FAILED:
            return _ENGINE
        try:
            from paddleocr import PaddleOCR
            try:
                # PaddleOCR 3.x
                # enable_mkldnn=False avoids a CPU runtime error ("ConvertPirAttribute2
                # RuntimeAttribute not support") seen with PaddlePaddle 3.x + oneDNN.
                # PADDLE_MODEL=mobile (default, fast) or server (more accurate, ~5x slower)
                kwargs = dict(
                    cpu_threads=int(os.environ.get("PADDLE_CPU_THREADS", "4")),
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    enable_mkldnn=False,
                    text_det_limit_type="max",
                    text_det_limit_side_len=int(os.environ.get("PADDLE_MAX_SIDE", "2000")),
                )
                variant = os.environ.get("PADDLE_MODEL", "mobile").lower()
                prefix = "PP-OCRv6_medium" if variant == "v6" else f"PP-OCRv5_{'server' if variant == 'server' else 'mobile'}"
                for kind, suffix in (("detection", "det"), ("recognition", "rec")):
                    name = f"{prefix}_{suffix}"
                    kwargs[f"text_{kind}_model_name"] = name
                    cache = Path(os.environ.get("PADDLE_PDX_CACHE_HOME", str(Path.home() / ".paddlex")))
                    local = cache / "official_models" / name
                    if (local / "inference.yml").exists():
                        kwargs[f"text_{kind}_model_dir"] = str(local)
                _ENGINE = PaddleOCR(**kwargs)
            except TypeError:
                # PaddleOCR 2.x
                _ENGINE = PaddleOCR(lang="en", use_angle_cls=True, show_log=False)
        except Exception as exc:
            print(f"[WARNING] PaddleOCR could not be started: {exc}")
            _ENGINE_FAILED = True
            _ENGINE = None
    return _ENGINE


def _run(engine, img):
    """Returns [(text, confidence, (x0, y0, x1, y1)), ...] for one image."""
    items = []
    if hasattr(engine, "predict"):
        # PaddleOCR 3.x
        for res in engine.predict(img):
            data = res if isinstance(res, dict) else getattr(res, "json", {}).get("res", {})
            if "res" in data and isinstance(data["res"], dict):
                data = data["res"]
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            polys = data.get("rec_polys", data.get("dt_polys", []))
            for t, sc, poly in zip(texts, scores, polys):
                pts = np.array(poly).reshape(-1, 2)
                items.append((str(t), float(sc),
                              (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())))
    else:
        # PaddleOCR 2.x
        result = engine.ocr(img, cls=True)
        for page in result or []:
            for box, (t, sc) in page or []:
                pts = np.array(box).reshape(-1, 2)
                items.append((str(t), float(sc),
                              (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())))
    return items


def _to_rows(items, min_conf):
    """Groups detected text pieces into reading-order lines (top to bottom, left to right)."""
    items = [it for it in items if it[1] >= min_conf and it[0].strip()]
    if not items:
        return []
    items.sort(key=lambda it: ((it[2][1] + it[2][3]) / 2.0, it[2][0]))
    rows, current, cur_y, cur_h = [], [], None, None
    for it in items:
        cy = (it[2][1] + it[2][3]) / 2.0
        hh = max(it[2][3] - it[2][1], 1.0)
        if current and abs(cy - cur_y) <= 0.6 * max(cur_h, hh):
            current.append(it)
            cur_y = (cur_y * (len(current) - 1) + cy) / len(current)
        else:
            if current:
                rows.append(current)
            current, cur_y, cur_h = [it], cy, hh
    if current:
        rows.append(current)
    out = []
    for r in rows:
        r = sorted(r, key=lambda p: p[2][0])
        seg = [r[0]]
        for prev, cur in zip(r, r[1:]):
            height = max(prev[2][3] - prev[2][1], cur[2][3] - cur[2][1], 1.0)
            # A big horizontal gap means a different column / panel: start a new line
            if cur[2][0] - prev[2][2] > 3.0 * height:
                out.append(" ".join(p[0].strip() for p in seg))
                seg = []
            seg.append(cur)
        out.append(" ".join(p[0].strip() for p in seg))
    return out


def paddle_text(img_bgr, min_conf=0.5):
    """
    Reads a BGR image with PaddleOCR (upright + rotated 90 degrees clockwise for
    sideways text).

    Returns (lines, words) where `lines` is a list of text lines and `words` is a
    list of (word, pixel_height) for the upright pass, used by the font-size rule.
    Returns ([], []) when PaddleOCR is unavailable.
    """
    engine = _get_engine()
    if engine is None:
        return [], []

    lines, words = [], []
    try:
        upright = _run(engine, img_bgr)
        lines.extend(_to_rows(upright, min_conf))
        for text, conf, (x0, y0, x1, y1) in upright:
            if conf >= min_conf:
                for w in text.split():
                    words.append((w, float(y1 - y0)))

        # Sideways text pass. Costs about as much as the upright pass, so in the default
        # "auto" setting it is skipped when the upright pass already found batch and
        # expiry/mfg text. PADDLE_ROTATED=always|auto|never
        rot_mode = os.environ.get("PADDLE_ROTATED", "auto").lower()
        low = " ".join(lines).lower()
        have_batch = any(k in low for k in ("b.no", "batch", "lot"))
        have_dates = any(k in low for k in ("exp", "mfg", "mfd"))
        if rot_mode == "always" or (rot_mode == "auto" and not (have_batch and have_dates)):
            rotated = _run(engine, cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE))
            lines.extend(_to_rows(rotated, min_conf))
    except Exception as exc:
        print(f"[WARNING] PaddleOCR failed on this image: {exc}")
    return lines, words


def engine_mode() -> str:
    mode = os.environ.get("OCR_ENGINE", "paddle").strip().lower()
    return mode if mode in ("tesseract", "auto", "paddle") else "paddle"



def extract_lines(img_bgr, min_conf=0.5):
    """Return original-image text boxes and confidence on a 0–100 scale.

    Paddle returns text-region boxes, not individual word boxes. Keep words empty
    rather than inventing word measurements for the font-size check.
    """
    engine = _get_engine()
    if engine is None:
        return [], ["PaddleOCR unavailable; using Tesseract fallback."]
    rows, warnings = [], []
    def collect(image, rotated=False):
        items = [item for item in _run(engine, image)
                 if item[1] >= min_conf and item[0].strip()
                 and item[2][3]-item[2][1] < 1.8 * max(1, item[2][2]-item[2][0])]
        # Assemble fragments in the OCR orientation before mapping sideways boxes.
        # Sorting mapped boxes by y would reverse/split a vertical batch/date line.
        groups = []
        for item in sorted(items, key=lambda it: (it[2][1]+it[2][3])/2):
            x0,y0,x1,y1 = item[2]
            cy, h = (y0+y1)/2, y1-y0
            target = next((g for g in reversed(groups)
                           if abs(cy-g[0]) < .45*min(h,g[1])), None)
            if target is None:
                groups.append([cy,h,[item]])
            else:
                target[2].append(item)
        for _, _, group in groups:
            segments = []
            for item in sorted(group,key=lambda it: it[2][0]):
                if segments:
                    prev = segments[-1][-1]
                    gap = item[2][0]-prev[2][2]
                    height = max(item[2][3]-item[2][1],prev[2][3]-prev[2][1])
                    if gap <= 1.2*height:
                        segments[-1].append(item)
                        continue
                segments.append([item])
            for segment in segments:
                text = " ".join(item[0].strip() for item in segment)
                confidence = sum(len(t)*c for t,c,_ in segment)/sum(len(t) for t,_,_ in segment)
                x0=min(it[2][0] for it in segment);y0=min(it[2][1] for it in segment)
                x1=max(it[2][2] for it in segment);y1=max(it[2][3] for it in segment)
                if rotated:
                    height = img_bgr.shape[0]
                    x0, y0, x1, y1 = y0, height-x1, y1, height-x0
                rows.append({"text": text, "confidence": round(confidence*100,1),
                             "box": [float(x0),float(y0),float(x1-x0),float(y1-y0)],
                             "source": "paddle_rotated" if rotated else "paddle",
                             "words": [], "alternatives": []})
    try:
        collect(img_bgr)
        mode = os.environ.get("PADDLE_ROTATED", "auto").lower()
        text = " ".join(row["text"] for row in rows).lower()
        complete = any(k in text for k in ("batch", "lot", "b.no")) and any(k in text for k in ("exp", "expiry"))
        if mode == "always" or (mode == "auto" and not complete):
            collect(cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE), rotated=True)
    except Exception as exc:
        warnings.append(f"PaddleOCR inference failed: {exc}")
    if not rows:
        warnings.append("PaddleOCR returned no text; using Tesseract fallback.")
    from ocr_pipeline import merge_lines
    return merge_lines(rows), warnings
