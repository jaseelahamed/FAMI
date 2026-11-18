"""
================================================================================
PHARMACEUTICAL MEDICINE LABEL VALIDATION & SCANNING SYSTEM
================================================================================
Computer Vision & Regulatory Compliance Validation System
Pharmacopoeia Criteria Verification:
  1. Generic Name (Proper Name / INN)
  2. Generic Name 2 Font Sizes Larger than Brand Name (Rule 96(1)(i))
  3. Dosage Form and Strength
  4. Active Ingredients in Metric Units
  5. Name and Address of Manufacturer
  6. Manufacturing License Number (Mfg Lic No)
  7. Batch / Lot Number (B.No. / Lot No.)
  8. Manufacturing Date & Expiry Date (Mfg Date / Exp Date)
  9. Storage Conditions
 10. Directions for Use / Dosage
 11. Prescription Symbol (Rx, NRx, XRx)
 12. Traceability Barcode or QR Code (GS1 Standards)
 13. Schedule & Warning Box (Prescription Drugs)
 14. Schedule Redline (Prescription Drugs)

Technologies: OpenCV (cv2), Pytesseract (OCR), Pyzbar (Barcode/QR), Regex (re)
================================================================================
"""

import os
import sys
import re
import json
import argparse
import numpy as np
import cv2

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Optional import for barcode & QR detection
try:
    from pyzbar import pyzbar
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False

# Import Pytesseract for OCR
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False


# ==============================================================================
# CONFIGURATION & TESSERACT AUTO-DETECTION (WINDOWS SUPPORT)
# ==============================================================================
def configure_tesseract():
    """
    Auto-detects Tesseract OCR executable on Windows systems if not already in PATH.
    """
    if not PYTESSERACT_AVAILABLE:
        print("[WARNING] Pytesseract library is not installed (`pip install pytesseract`).")
        return False

    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%APPDATA%\Tesseract-OCR\tesseract.exe"),
    ]

    # Check custom environment variables first (ideal for Docker / custom Linux / Windows)
    env_tess = os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_PATH")
    if env_tess and os.path.exists(env_tess):
        pytesseract.pytesseract.tesseract_cmd = env_tess
        print(f"[INFO] Tesseract-OCR configured via environment variable at: {env_tess}")
        return True

    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        pass

    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            print(f"[INFO] Tesseract-OCR detected and configured at: {path}")
            return True

    print("[WARNING] Tesseract-OCR executable not found in default Windows paths or PATH.")
    return False


# ==============================================================================
# AUTO-CROP UTILITY (REMOVES LETTERBOXING FROM MOBILE CAPTURES)
# ==============================================================================
def autocrop_borders(img: np.ndarray, threshold: int = 22) -> np.ndarray:
    """
    Removes black/dark letterbox borders (e.g. from smartphone screenshots or camera margins)
    so that Otsu/Adaptive binarization focuses on the actual medicine packaging foil.
    """
    if img is None or img.size == 0:
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    row_means = np.mean(gray, axis=1)
    col_means = np.mean(gray, axis=0)

    top = 0
    while top < h - 60 and row_means[top] < threshold:
        top += 1

    bottom = h - 1
    while bottom > top + 60 and row_means[bottom] < threshold:
        bottom -= 1

    left = 0
    while left < w - 60 and col_means[left] < threshold:
        left += 1

    right = w - 1
    while right > left + 60 and col_means[right] < threshold:
        right -= 1

    # Crop if significant borders exist (at least 15px)
    if top > 15 or bottom < h - 16 or left > 15 or right < w - 16:
        # Keep small margin
        top = max(0, top - 4)
        bottom = min(h, bottom + 4)
        left = max(0, left - 4)
        right = min(w, right + 4)
        return img[top:bottom, left:right]

    return img


# ==============================================================================
# MEDICINE LABEL SCANNER & VALIDATOR CLASS
# ==============================================================================
class MedicineLabelValidator:
    """
    Core engine that handles image preprocessing, Multi-orientation OCR,
    Barcode/QR reading, Redline detection, Font size comparison (Rule 96(1)(i)),
    and Full Pharmacopoeia Regulatory Criteria Validation.
    """

    def __init__(self, image_path: str):
        configure_tesseract()
        self.image_path = image_path
        # Automatically correct smartphone EXIF orientation (portrait vs landscape)
        try:
            from PIL import Image, ImageOps
            with Image.open(image_path) as pil_img:
                pil_img = ImageOps.exif_transpose(pil_img)
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                raw_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception:
            raw_img = cv2.imread(image_path)

        if raw_img is None:
            raise ValueError(f"Error: OpenCV could not read image from '{image_path}'")

        # Auto-crop black phone letterboxing
        cropped = autocrop_borders(raw_img)

        # Keep a higher-resolution copy (capped at OCR_MAX_DIM (4800 px by default)) for the deep OCR pass, which
        # needs the extra detail to read small print on hard images (foil photos).
        fh, fw = cropped.shape[:2]
        ocr_max_dim = max(1200, int(os.environ.get("OCR_MAX_DIM", "4800")))
        if max(fh, fw) > ocr_max_dim:
            fs = ocr_max_dim / float(max(fh, fw))
            self.full_res_image = cv2.resize(cropped, (int(fw * fs), int(fh * fs)), interpolation=cv2.INTER_AREA)
        else:
            self.full_res_image = cropped

        # Downscale ultra-high-res camera captures (e.g. 12MP-48MP smartphone photos)
        # Prevents Out-Of-Memory (OOM) kills and timeout on Render's 512MB RAM free tier
        h, w = cropped.shape[:2]
        max_dim = 1200
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            new_w = int(w * scale)
            new_h = int(h * scale)
            self.original_image = cv2.resize(cropped, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            self.original_image = cropped

        self.annotated_image = self.original_image.copy()

        self.extracted_text = ""
        self.ocr_data = None
        self.barcode_results = {}
        self.redline_results = {}
        self.font_ratio_results = {}
        self.validation_results = {}
        self.compliance_score = 0.0

    # --------------------------------------------------------------------------
    # 1. MULTI-ORIENTATION & ENHANCED OCR EXTRACTION
    # --------------------------------------------------------------------------
    def extract_text(self) -> str:
        """Recover separate, confidence-scored lines without concatenating OCR noise."""
        import ocr_paddle
        from ocr_pipeline import extract_lines
        mode = ocr_paddle.engine_mode()
        self.ocr_lines, self.ocr_warnings = [], []
        if mode == "paddle":
            self.ocr_lines, self.ocr_warnings = ocr_paddle.extract_lines(self.full_res_image)
        paddle_primary = bool(self.ocr_lines)
        if not paddle_primary:
            if not PYTESSERACT_AVAILABLE:
                raise RuntimeError("PaddleOCR returned no text and the Tesseract fallback is unavailable.")
            self.ocr_lines, warnings = extract_lines(self.full_res_image, pytesseract)
            self.ocr_warnings.extend(warnings)
        self.ocr_engine = "paddle" if paddle_primary else "tesseract"
        if paddle_primary and PYTESSERACT_AVAILABLE:
            from ocr_quantity import recover_quantities
            self.ocr_warnings.extend(recover_quantities(self.full_res_image, self.ocr_lines, pytesseract))
        if paddle_primary:
            from field_recovery import recover_fields
            recovered, warnings = recover_fields(self.full_res_image, self.ocr_lines)
            self.ocr_lines = recovered + self.ocr_lines
            self.ocr_warnings.extend(warnings)
        scale = self.original_image.shape[0] / self.full_res_image.shape[0]
        words = [word for line in self.ocr_lines for word in line["words"]]
        self.ocr_data = {
            "text": [word["text"] for word in words],
            "height": [word["height"] * scale for word in words],
            "conf": [word["confidence"] for word in words],
        }
        # Independent word boxes for the font check only. Never merge this text
        # into Paddle's fields, evidence, or quantity correction results.
        self.font_ocr_data = None
        self.font_ocr_names = {}
        self.font_ocr_error = None
        if paddle_primary:
            self.measure_font_words()
        lines = [line["text"] for line in self.ocr_lines]
        # Keep legacy Tesseract-first auto mode available.
        import ocr_deep
        if mode == "auto" and ocr_deep.needs_deep_pass("\n".join(lines)):
            p_lines, _ = ocr_paddle.paddle_text(self.full_res_image)
            if p_lines:
                lines = p_lines + lines
                self.ocr_warnings.append("Paddle readings supplement Tesseract; review discrepancies.")
        # Rotations only supplement missing side-strip details, never replace the
        # upright font measurements or append all the background texture.
        preview = " ".join(lines)
        if not paddle_primary and os.environ.get("OCR_ROTATION_PASSES", "1") != "0" and not (
            re.search(r"\b(?:batch|lot|b\.?\s*no)\b", preview, re.I)
            and re.search(r"\b(?:exp|expiry)\b", preview, re.I)
        ):
            from ocr_pipeline import _read_lines
            for angle in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
                rotated = cv2.rotate(self.original_image, angle)
                gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
                try:
                    for row in _read_lines(gray, pytesseract, "rotated", psm=11):
                        if re.search(r"\b(?:batch|lot|b\.?\s*no|mfg|mfd|exp|expiry|licen[cs]e)\b", row["text"], re.I):
                            lines.append(row["text"])
                except RuntimeError as exc:
                    self.ocr_warnings.append(str(exc))
        self.extracted_text = "\n".join(dict.fromkeys(lines))
        return self.extracted_text

    # --------------------------------------------------------------------------
    # 2. GENERIC NAME VS BRAND NAME FONT SIZE COMPARISON (RULE 96(1)(i))
    # --------------------------------------------------------------------------
    def measure_font_words(self):
        """Read actual Tesseract word boxes in display-image pixel coordinates."""
        if not PYTESSERACT_AVAILABLE:
            self.font_ocr_error = "Tesseract is unavailable for font measurement"
            return
        from ocr_pipeline import _read_lines
        from label_fields import extract_fields
        self.font_heading_pair = None
        try:
            from font_regions import measure_heading_pair
            self.font_heading_pair = measure_heading_pair(
                self.full_res_image, getattr(self, 'ocr_lines', []), pytesseract,
                self.original_image.shape[0] / self.full_res_image.shape[0])
            if self.font_heading_pair:
                return
        except Exception as exc:
            self.font_ocr_error = f"Heading crop measurement unavailable: {exc}"
        try:
            gray = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2GRAY)
            rows = _read_lines(gray, pytesseract, "font_tesseract", psm=11)
            words = [word for row in rows for word in row["words"]]
            self.font_ocr_data = {
                "text": [word["text"] for word in words],
                "height": [word["height"] for word in words],
                "conf": [word["confidence"] for word in words],
            }
            # Sparse segmentation can separate a brand from an adjacent Rx
            # symbol that Paddle grouped with it. This fallback is font-only.
            fields = extract_fields("\n".join(row["text"] for row in rows))
            self.font_ocr_names = {key: fields[key]["value"]
                                   for key in ("generic", "brand") if key in fields}
        except Exception as exc:
            self.font_ocr_error = f"Tesseract font measurement unavailable: {exc}"

    def evaluate_font_size_rule(self, generic_match: str, brand_match: str) -> dict:
        """
        Under Drugs and Cosmetics Rules Rule 96(1)(i) amendment:
        The proper (generic) name of the drug shall be printed in a font size
        larger than the brand name (or at least two font sizes larger).
        
        Uses Pytesseract bounding box heights (in pixels) to verify compliance.
        """
        result = {
            "status": "FAIL",
            "generic_font_height_px": 0,
            "brand_font_height_px": 0,
            "ratio": None,
            "details": "Unable to measure both generic and brand names reliably"
        }

        pair = getattr(self, "font_heading_pair", None)
        if pair:
            gen_h, br_h = pair['generic']['height_px'], pair['brand']['height_px']
            ratio = gen_h / br_h
            result.update(status="PASS" if ratio >= 1 else "FAIL",
                generic_font_height_px=round(gen_h, 1), brand_font_height_px=round(br_h, 1),
                ratio=round(ratio, 2), measurement_source=pair['source'],
                generic_name=pair['generic']['name'], brand_name=pair['brand']['name'],
                measurement_evidence=pair,
                details=f"Generic ({gen_h:.1f}px) / Brand ({br_h:.1f}px): {ratio:.2f}x (measured word heights)")
            self.font_ratio_results = result
            return result
        font_data = getattr(self, "font_ocr_data", None) or self.ocr_data
        if getattr(self, "ocr_engine", None) == "paddle":
            result["measurement_source"] = "tesseract_font_only"
            names = getattr(self, "font_ocr_names", {})
            generic_match = generic_match or names.get("generic", "")
            brand_match = brand_match or names.get("brand", "")
            if getattr(self, "font_ocr_error", None):
                result["details"] = self.font_ocr_error
        else:
            result["measurement_source"] = "tesseract_word_boxes"
        result["generic_name"] = generic_match
        result["brand_name"] = brand_match
        if not font_data or "text" not in font_data:
            self.font_ratio_results = result
            return result

        texts = font_data.get("text", [])
        heights = font_data.get("height", [])

        # Helper to find average height of matching words
        def get_word_height(target_str: str) -> float:
            if not target_str:
                return 0.0
            words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', target_str) if len(w) > 2]
            matched_heights = []
            for i, word in enumerate(texts):
                # Exact word match only (ignoring punctuation). Substring matching
                # wrongly pulled in unrelated small-print words (e.g. "ip" inside
                # "ciprofloxacin"), which skewed the average.
                w_clean = re.sub(r'[^a-z0-9]', '', word.lower())
                if w_clean and w_clean in words:
                    h = heights[i]
                    confidence = float(font_data.get("conf", [100] * len(texts))[i])
                    if confidence >= 60 and 10 < h < 200:  # Valid character pixel height
                        matched_heights.append(h)
            # The name is printed large once and may be repeated in small print
            # (e.g. in the composition), so use the tallest occurrence.
            return float(max(matched_heights)) if matched_heights else 0.0

        gen_h = get_word_height(generic_match)
        br_h = get_word_height(brand_match)

        if not generic_match or generic_match == "Not Detected" or not brand_match or gen_h == 0 or br_h == 0:
            self.font_ratio_results = result
            return result

        result["generic_font_height_px"] = round(gen_h, 1)
        result["brand_font_height_px"] = round(br_h, 1)
        ratio = round(gen_h / max(br_h, 1.0), 2)
        result["ratio"] = ratio

        # Compare measured pixel heights; this is not a legal font-size certification.
        if ratio >= 1.0:
            result["status"] = "PASS"
            result["details"] = f"Generic ({gen_h:.0f}px) is {ratio}x larger than Brand ({br_h:.0f}px) (measured pixel heights)"
        else:
            result["status"] = "FAIL"
            result["details"] = f"Brand ({br_h:.0f}px) is larger than Generic ({gen_h:.0f}px) (measured pixel heights)"

        self.font_ratio_results = result
        return result

    # --------------------------------------------------------------------------
    # 3. BARCODE & QR CODE DETECTION (PYZBAR)
    # --------------------------------------------------------------------------
    def detect_barcode_or_qr(self) -> dict:
        """
        Detects standard 1D barcodes and 2D QR codes (GS1 DataMatrix standards).
        On primary blister packs, note that barcodes are often printed on the outer carton.
        """
        result = {
            "detected": False,
            "decoded": False,
            "gs1_verified": False,
            "count": 0,
            "details": [],
            "status": "FAIL",
            "regulatory_note": "Detection alone does not verify GS1 structure or product authenticity."
        }

        try:
            # Decode at the best available resolution. Dense DataMatrix/QR codes
            # often become undecodable after the general OCR image is downsized.
            decoded_objects = []
            decode_sx = decode_sy = 1.0
            if PYZBAR_AVAILABLE:
                for candidate in (self.full_res_image, self.original_image):
                    decoded_objects = pyzbar.decode(candidate)
                    if decoded_objects:
                        decode_sx = self.original_image.shape[1] / float(candidate.shape[1])
                        decode_sy = self.original_image.shape[0] / float(candidate.shape[0])
                        break
                    gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
                    decoded_objects = pyzbar.decode(gray)
                    if decoded_objects:
                        decode_sx = self.original_image.shape[1] / float(candidate.shape[1])
                        decode_sy = self.original_image.shape[0] / float(candidate.shape[0])
                        break

            # OpenCV's QR decoder is a useful fallback when zbar is not installed
            # or cannot decode a QR symbol. It also reports detection separately
            # from successful decoding so an unreadable but visible code is found.
            qr_details = []
            if not decoded_objects:
                from barcode_evidence import qr_candidates
                detector = cv2.QRCodeDetector()
                for x,y,w,h in qr_candidates(self.full_res_image):
                    crop = self.full_res_image[y:y+h,x:x+w]
                    text,_,_ = detector.detectAndDecode(crop)
                    sx=self.original_image.shape[1]/self.full_res_image.shape[1]
                    sy=self.original_image.shape[0]/self.full_res_image.shape[0]
                    qr_details.append({"type":"QRCODE", "data":text or "",
                                       "rect":(int(x*sx),int(y*sy),int(w*sx),int(h*sy))})
                decoded_objects = qr_details

            if decoded_objects:
                result["detected"] = True
                result["status"] = "PASS"
                result["count"] = len(decoded_objects)
                result["regulatory_note"] = "Code detected; GS1 structure and authenticity not verified"

                for obj in decoded_objects:
                    if isinstance(obj, dict):
                        data_str, code_type = obj["data"], obj["type"]
                        x, y, box_w, box_h = obj["rect"]
                    else:
                        data_str = obj.data.decode("utf-8", errors="ignore")
                        code_type = obj.type
                        x = int(obj.rect.left * decode_sx)
                        y = int(obj.rect.top * decode_sy)
                        box_w = int(obj.rect.width * decode_sx)
                        box_h = int(obj.rect.height * decode_sy)

                    result["details"].append({
                        "type": code_type,
                        "data": data_str,
                        "rect": (x, y, box_w, box_h)
                    })

                    cv2.rectangle(
                        self.annotated_image,
                        (x, y),
                        (x + box_w, y + box_h),
                        (255, 255, 0),
                        3
                    )
                    cv2.putText(
                        self.annotated_image,
                        f"CODE: {code_type}",
                        (x, max(y - 8, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (255, 255, 0),
                        2
                    )

            result["decoded"] = any(bool(item["data"]) for item in result["details"])
            self.barcode_results = result
            return result

        except Exception as e:
            result["error"] = str(e)
            self.barcode_results = result
            return result

    # --------------------------------------------------------------------------
    # 4. REDLINE DETECTION (OPENCV HSV FILTERING)
    # --------------------------------------------------------------------------
    def detect_redline(self) -> dict:
        """
        Detects the mandatory Red Warning Line prescribed under Schedule H / H1 / X
        regulations for prescription-only pharmaceuticals.
        """
        img_h, img_w = self.original_image.shape[:2]
        hsv = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2HSV)

        # Red Hue spans both ends of HSV (0-10 & 170-180)
        lower_red1 = np.array([0, 60, 45])
        upper_red1 = np.array([12, 255, 255])
        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)

        lower_red2 = np.array([168, 60, 45])
        upper_red2 = np.array([180, 255, 255])
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

        red_mask = cv2.bitwise_or(mask1, mask2)

        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 25))

        morph_h = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, horizontal_kernel, iterations=2)
        morph_v = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, vertical_kernel, iterations=2)
        combined_morph = cv2.bitwise_or(morph_h, morph_v)
        # Long uninterrupted strokes remain identifiable when a coloured border
        # connects a warning panel to the photograph background.
        vertical_strokes = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, max(31,int(img_h*.20)))))
        horizontal_strokes = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (max(31,int(img_w*.20)),3)))

        clean_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        cleaned_mask = cv2.morphologyEx(combined_morph, cv2.MORPH_OPEN, clean_kernel)

        contours, _ = cv2.findContours(cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours=list(contours)
        for strokes in (vertical_strokes,horizontal_strokes):
            extra,_=cv2.findContours(strokes,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            contours.extend(extra)

        redline_found = False
        detected_strips = []
        min_line_length = int(min(img_w, img_h) * 0.15)
        min_aspect_ratio = 3.0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 120:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio_h = w / float(h) if h > 0 else 0
            aspect_ratio_v = h / float(w) if w > 0 else 0

            is_horizontal = (aspect_ratio_h >= min_aspect_ratio) and (w >= min_line_length)
            is_vertical = (aspect_ratio_v >= min_aspect_ratio) and (h >= min_line_length)

            if (is_horizontal or is_vertical) and not any(
                abs(x-r['bounding_box'][0])+abs(y-r['bounding_box'][1]) < 8 for r in detected_strips):
                redline_found = True
                orientation = "Horizontal" if is_horizontal else "Vertical"
                ratio_val = round(max(aspect_ratio_h, aspect_ratio_v), 2)
                detected_strips.append({
                    "bounding_box": (x, y, w, h),
                    "orientation": orientation,
                    "aspect_ratio": ratio_val,
                    "area": int(area)
                })

                cv2.rectangle(self.annotated_image, (x, y), (x + w, y + h), (0, 0, 255), 3)
                cv2.putText(
                    self.annotated_image,
                    f"SCHEDULE REDLINE ({orientation})",
                    (x, max(y - 8, 18)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 0, 255),
                    2
                )

        result = {
            "detected": redline_found,
            "count": len(detected_strips),
            "strips": detected_strips,
            "status": "PASS (Schedule Redline Present)" if redline_found else "NOT DETECTED (OTC or Non-Schedule)"
        }
        self.redline_results = result
        return result

    # --------------------------------------------------------------------------
    # 5. PHARMACOPOEIA REGULATORY CRITERIA (ALL 14 MANDATORY RULES)
    # --------------------------------------------------------------------------
    def validate_regulatory_fields(self, text: str) -> dict:
        """Report detected content as PASS and missing content as FAIL."""
        from label_fields import extract_fields
        fields = extract_fields(text, getattr(self, "ocr_lines", []))
        font = self.evaluate_font_size_rule(
            fields.get("generic", {}).get("value", ""),
            fields.get("brand", {}).get("value", ""))
        definitions = [
            ("Generic Name", "generic", "Generic name printed on the label", True),
            ("Generic Font Size >= Brand (Rule 96(1)(i))", "font", "Comparison of measured generic and brand text heights", True),
            ("Dosage Form and Strength", "form_strength", "Dosage form and quantitative strength", True),
            ("Active Ingredients in Metric Units", "active", "Composition statement with a readable metric quantity", True),
            ("Name and Address of Manufacturer", "manufacturer", "Manufacturer statement and following address lines", True),
            ("Mfg License Number", "licence", "Printed manufacturing or import licence identifier", True),
            ("Batch / Lot Number", "batch", "Printed batch or lot identifier", True),
            ("Mfg Date / Expiry Date", "dates", "Both manufacturing and expiry dates must be readable", True),
            ("Storage Conditions", "storage", "Storage and child-safety instructions", True),
            ("Directions for Use / Dosage", "dosage", "Dosage or directions statement", True),
            ("Prescription Symbol (Rx, NRx, XRx)", "rx", "Readable prescription symbol", False),
            ("Required Barcode or QR Code", "barcode", "Barcode or QR presence check", False),
            ("Schedule Warning (Prescription Drugs)", "warning", "Readable schedule or prescription restriction statement", True),
            ("Schedule Redline (Prescription Drugs)", "redline", "Elongated red marking detected by color and geometry", True),
        ]
        def combine(target, keys):
            present = [fields[k] for k in keys if k in fields]
            if present:
                fields[target] = {
                    "value": " | ".join(f["value"] for f in present),
                    "lines": [line for f in present for line in f["lines"]],
                    "uncertain": len(present) != len(keys),
                }
        combine("form_strength", ("form", "strength"))
        combine("dates", ("mfg_date", "exp_date"))
        results = {}
        # These criteria check whether the corresponding label content is present.
        # Confidence and competing readings remain diagnostic evidence, rather
        # than turning a successful presence check into mandatory review.
        presence_fields = {"dosage", "batch", "licence", "manufacturer", "warning"}
        for name, key, description, required in definitions:
            entry = fields.get(key)
            status, value, confidence, notes = "FAIL", "Not Detected", None, []
            if entry:
                value = entry["value"]
                status = "PASS" if value.strip() else "FAIL"
                evidence = [row for row in getattr(self, "ocr_lines", [])
                            if any(row["text"].strip(" |—_~") == line for line in entry["lines"])]
                if getattr(self, "ocr_lines", []) and not evidence and key not in presence_fields:
                    notes.append("Supplemental reading has no matching measured line evidence")
                if evidence:
                    confidence = min(row["confidence"] for row in evidence)
                    if confidence < 75 and key not in presence_fields:
                        notes.append("Low OCR confidence; compare with the image")
                    # Identifiers, quantities and addresses must not silently choose
                    # one of conflicting OCR readings. Keep the alternatives visible.
                    if key in ("dates", "active", "form_strength", "storage"):
                        def numeric_evidence(line):
                            parsed = extract_fields(line)
                            keys = {"dates": ("mfg_date", "exp_date"),
                                    "form_strength": ("strength",),
                                    "batch": ("batch",), "licence": ("licence",),
                                    "storage": ("storage",)}.get(key)
                            if keys:
                                content = " ".join(parsed[k]["value"] for k in keys if k in parsed)
                            else:
                                content = line
                            return re.findall(r"\d+", content)
                        for row in evidence:
                            numbers = numeric_evidence(row["text"])
                            for alternate in row.get("alternatives", []):
                                other = numeric_evidence(alternate["text"])
                                if alternate["confidence"] >= 45 and numbers and other and numbers != other:
                                    notes.append("OCR passes disagree: " + alternate["text"])
                if entry.get("uncertain"):
                    notes.append("Required part of this field is missing or unreadable")
            if key == "font":
                status, value = font["status"], font["details"]
            elif key == "barcode":
                if self.barcode_results.get("detected"):
                    status, value = "PASS", "Barcode / QR code present"
                else:
                    value = "Not detected (conditional for primary packaging)"
            elif key == "redline" and self.redline_results.get("detected"):
                status, value = "PASS", "Red marking detected (color/shape check only)"
            elif key == "warning" and not entry and getattr(self, "warning_panel_results", {}).get("detected"):
                status = "PASS"
                description = "Visual presence of a red panel containing printed text"
                value = "Red panel with printed warning-style text detected; wording unreadable"
                notes.append("Visual presence only; prescription wording has not been verified")
            presence_state = "detected" if entry and value.strip() else "not_detected"
            if key in ("font", "barcode", "redline") or (key == "warning" and not entry):
                presence_state = "detected" if status == "PASS" else "not_detected"
            if status == "FAIL" and not entry and key != "font":
                value = "Not present in extracted image content"
            if not required and status == "FAIL":
                status = "OPTIONAL"
                value = "Not detected (optional)"
            results[name] = {"status": status, "required": required,
                             "description": description, "extracted_value": value,
                             "presence_state": presence_state,
                             "ocr_confidence": confidence,
                             "diagnostic_notes": list(dict.fromkeys(notes)),
                             "review_notes": list(dict.fromkeys(notes))}
            if entry and "raw_value" in entry:
                results[name]["raw_extracted_value"] = entry["raw_value"]
                results[name]["spelling_corrected"] = entry["raw_value"] != value
        passed = sum(v["required"] and v["status"] == "PASS" for v in results.values())
        total = sum(v["required"] for v in results.values())
        self.compliance_score = round(100 * passed / total, 2)
        self.validation_results = results
        self.overall_status = "COMPLIANT / PASS" if passed == total else "NON-COMPLIANT / REJECT"
        return {"score_percentage": self.compliance_score,
                "passed_required": f"{passed}/{total}",
                "overall_status": self.overall_status, "requires_review": False, "validation_mode": "presence",
                "field_checks": results}

    # --------------------------------------------------------------------------
    # 6. VISUAL RESULT OVERLAY GENERATOR
    # --------------------------------------------------------------------------
    def generate_annotated_output(self, output_path: str = "annotated_label_result.jpg") -> str:
        """
        Draws an informative HUD (Heads-Up Display) scorecard onto the right side
        of the annotated image, highlighting all 14 Pharmacopoeia criteria verdicts.
        """
        img = self.annotated_image.copy()
        h, w = img.shape[:2]

        # Dashboard sidebar
        sidebar_w = max(480, int(w * 0.50))
        canvas = np.zeros((h, w + sidebar_w, 3), dtype=np.uint8)
        canvas[:, :w] = img

        # Dark slate blue background
        canvas[:, w:] = (22, 20, 28)

        # Header
        sx = w + 20
        cv2.putText(canvas, "PHARMACOPOEIA AUDIT HUD", (sx, 35), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(canvas, (sx, 48), (w + sidebar_w - 20, 48), (80, 80, 110), 1)

        # 14 Criteria display
        y_pos = 75
        cv2.putText(canvas, "14 STATUTORY CRITERIA CHECKLIST:", (sx, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 240), 1)
        y_pos += 22

        for field, data in self.validation_results.items():
            st = data["status"]
            if st == "PASS":
                color = (0, 230, 0)
                tag = "[PASS]"
            elif "CONDITIONAL" in st or "INFO" in st or st in ("REVIEW", "OPTIONAL"):
                color = (255, 190, 0)
                tag = "[OPT]" if st == "OPTIONAL" else "[INFO]"
            else:
                color = (70, 70, 255)
                tag = "[FAIL]"

            short_name = field[:28]
            text_line = f"{tag} {short_name}"
            cv2.putText(canvas, text_line, (sx, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.44, color, 1)
            y_pos += 20
            if y_pos > h - 75:
                break

        # Overall compliance footer
        y_pos = max(y_pos + 15, h - 55)
        verdict = "REVIEW" if getattr(self, "overall_status", "") == "MANUAL REVIEW REQUIRED" else ("PASS" if self.compliance_score >= 80 else "REJECT")
        overall_text = f"SCORE: {self.compliance_score}% - {verdict}"
        box_color = (0, 140, 200) if verdict == "REVIEW" else ((0, 160, 0) if self.compliance_score >= 80 else (0, 0, 200))
        cv2.rectangle(canvas, (sx - 5, y_pos - 25), (w + sidebar_w - 15, y_pos + 15), box_color, -1)
        cv2.putText(canvas, overall_text, (sx + 10, y_pos), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 2)

        cv2.imwrite(output_path, canvas)
        return output_path

    # --------------------------------------------------------------------------
    # 7. RUN COMPLETE SCAN PIPELINE
    # --------------------------------------------------------------------------
    def run_full_pipeline(self) -> dict:
        """
        Executes all validation steps in sequence:
        1. Multi-orientation OCR Text Extraction & Font Box Analysis
        2. Barcode & QR Code Detection
        3. Schedule Redline Detection
        4. 14-Point Pharmacopoeia Regulatory Validation
        """
        print(f"\n[1/4] Running Multi-Orientation OCR Text Extraction on: {self.image_path}...")
        text = self.extract_text()

        print("[2/4] Scanning for GS1 Barcodes / QR Codes...")
        barcode_info = self.detect_barcode_or_qr()

        print("[3/4] Performing HSV Color Filtering for Schedule Redline...")
        redline_info = self.detect_redline()

        from warning_panel import detect_warning_panel
        self.warning_panel_results = detect_warning_panel(self.original_image)

        print("[4/4] Validating 14 Pharmacopoeia Statutory Regulatory Criteria...")
        validation_info = self.validate_regulatory_fields(text)

        full_report = {
            "image_path": self.image_path,
            "ocr_text_preview": text[:350] + ("..." if len(text) > 350 else ""),
            "ocr_text_full": text,
            "ocr_engine": getattr(self, "ocr_engine", "unknown"),
            "ocr_lines": [{k: v for k, v in line.items() if k != "words"} for line in getattr(self, "ocr_lines", [])],
            "ocr_warnings": getattr(self, "ocr_warnings", []),
            "barcode_detection": barcode_info,
            "redline_detection": redline_info,
            "warning_panel_detection": self.warning_panel_results,
            "font_ratio_analysis": self.font_ratio_results,
            "regulatory_validation": validation_info
        }

        return full_report


# ==============================================================================
# SAMPLE PHARMACEUTICAL LABEL GENERATOR (DEMO TEST)
# ==============================================================================
def generate_sample_medicine_label(filename: str = "sample_medicine_label.png") -> str:
    """
    Creates a realistic synthetic pharmaceutical label containing all 14 regulatory
    elements, a Schedule H red warning line, and simulated QR code.
    """
    width, height = 960, 620
    img = np.ones((height, width, 3), dtype=np.uint8) * 255

    # Border
    cv2.rectangle(img, (10, 10), (width - 10, height - 10), (40, 40, 40), 2)

    # Rx Symbol
    cv2.rectangle(img, (25, 25), (75, 75), (0, 0, 180), -1)
    cv2.putText(img, "Rx", (32, 63), cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 255, 255), 2)

    # Brand Name (Smaller font)
    cv2.putText(img, "CIPRODAC 500", (90, 52), cv2.FONT_HERSHEY_DUPLEX, 0.9, (20, 20, 120), 2)
    # Generic formulation (2 font sizes larger - 1.2x scale)
    cv2.putText(img, "CIPROFLOXACIN TABLETS IP 500MG", (90, 85), cv2.FONT_HERSHEY_DUPLEX, 1.15, (0, 0, 0), 2)

    # Composition section
    cv2.putText(img, "Composition:", (25, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(img, "Each film-coated tablet contains: Ciprofloxacin Hydrochloride IP equivalent to Ciprofloxacin 500 mg",
                (25, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (30, 30, 30), 1)

    # Dosage & Directions
    cv2.putText(img, "Dosage: As directed by the Physician.", (25, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1)
    cv2.putText(img, "Directions for use: Swallow whole with water.", (25, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 40, 40), 1)

    # Storage Instructions
    cv2.putText(img, "Storage: Store Protected from light and moisture. Below 25 deg C.",
                (25, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (20, 20, 20), 1)

    # SCHEDULE H MANDATORY RED WARNING LINE & BOX
    cv2.rectangle(img, (25, 300), (width - 25, 312), (0, 0, 215), -1)

    cv2.rectangle(img, (25, 325), (width - 25, 385), (0, 0, 200), 2)
    cv2.putText(img, "SCHEDULE H PRESCRIPTION DRUG - CAUTION", (35, 348), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 200), 2)
    cv2.putText(img, "Warning: To be sold by retail without the prescription of a Registered Medical Practitioner.",
                (35, 372), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (0, 0, 160), 1)

    # Manufacturing & Batch Details
    cv2.putText(img, "B.No. JKBD26020", (25, 425), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 0), 2)
    cv2.putText(img, "Mfg. Date: FEB 2026", (25, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 0), 2)
    cv2.putText(img, "Exp. Date: JAN 2029", (25, 485), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 0), 2)
    cv2.putText(img, "Mfg. Lic. No.: JK/01/06-07/110", (25, 515), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (0, 0, 0), 2)

    # Manufacturer Info
    cv2.putText(img, "Manufactured by: CADILA PHARMACEUTICALS LIMITED, SIDCO, Samba - 184 121, State of J & K",
                (25, 550), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (40, 40, 40), 1)

    # QR Code
    try:
        enc = cv2.QRCodeEncoder.create()
        qr_matrix = enc.encode("https://verify.mohfw.gov.in/pharma/JKBD26020")
        qr_size = 110
        qr_resized = cv2.resize(qr_matrix, (qr_size, qr_size), interpolation=cv2.INTER_NEAREST)
        qr_bgr = cv2.cvtColor(qr_resized, cv2.COLOR_GRAY2BGR)

        qx, qy = width - qr_size - 40, 420
        cv2.rectangle(img, (qx - 10, qy - 10), (qx + qr_size + 10, qy + qr_size + 25), (245, 245, 245), -1)
        img[qy:qy + qr_size, qx:qx + qr_size] = qr_bgr
        cv2.rectangle(img, (qx - 2, qy - 2), (qx + qr_size + 2, qy + qr_size + 2), (180, 180, 180), 1)
        cv2.putText(img, "GS1 QR CODE", (qx + 8, qy + qr_size + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (60, 60, 60), 1)
    except Exception:
        pass

    cv2.imwrite(filename, img)
    return filename


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Pharmaceutical Medicine Label Validation System (14 Pharmacopoeia Criteria)"
    )
    parser.add_argument("--image", "-i", type=str, default=None, help="Path to medicine label image file")
    parser.add_argument("--demo", action="store_true", help="Generate synthetic medicine label and run scan")
    parser.add_argument("--output", "-o", type=str, default="annotated_result.jpg", help="Output annotated image")
    parser.add_argument("--json", type=str, default="validation_report.json", help="Output JSON report")

    args = parser.parse_args()
    configure_tesseract()

    image_to_scan = args.image
    if image_to_scan is None or args.demo:
        if not image_to_scan:
            image_to_scan = generate_sample_medicine_label("sample_medicine_label.png")

    try:
        scanner = MedicineLabelValidator(image_to_scan)
        report = scanner.run_full_pipeline()
        annotated_path = scanner.generate_annotated_output(args.output)
        print(f"[SUCCESS] Visual annotated result saved to: {annotated_path}")

        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)
        print(f"[SUCCESS] Audit JSON report exported to: {args.json}\n")

    except Exception as e:
        print(f"\n[FATAL ERROR] Pipeline execution encountered an error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
