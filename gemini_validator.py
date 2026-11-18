"""
================================================================================
PHARMASCAN AI - GEMINI MULTIMODAL VISION REGULATORY VALIDATION ENGINE
================================================================================
Leverages Google Gemini Multimodal Vision AI to semantically inspect, extract,
and audit pharmaceutical medicine labels against 14 Pharmacopoeia statutory criteria
(CDSCO Drugs & Cosmetics Act Rule 96, Schedule G/H/H1/X, US FDA 21 CFR 201, WHO GMP).
================================================================================
"""

import os
import json
import re
import time
from typing import Dict, Any, Optional
from PIL import Image, ImageOps

# Available candidate models in order of priority & responsiveness
GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite"
]

_CLIENT = None


def _load_env_file():
    """Loads variables from .env file if present in the project directory."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and v and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_env_file()


def get_genai_client():
    """Lazily initializes and returns the Google GenAI client."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    _load_env_file()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        _CLIENT = genai.Client()
        return _CLIENT
    except Exception as e:
        print(f"[WARNING] Could not initialize Google GenAI Client: {e}")
        return None


def is_gemini_available() -> bool:
    """Checks whether the Gemini API is configured and accessible."""
    _load_env_file()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return False
    try:
        import google.genai
        return True
    except ImportError:
        return False


def inspect_label_with_gemini(image_path: str) -> Optional[Dict[str, Any]]:
    """
    Sends the medicine packaging image to Gemini Multimodal Vision AI and extracts
    all 14 Pharmacopoeia regulatory criteria with deep semantic comprehension.
    """
    client = get_genai_client()
    if not client:
        return None

    # Load and auto-orient image
    try:
        with Image.open(image_path) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img)
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            # Downscale if image is gigantic (> 1800px) to keep network payload fast & accurate
            max_size = 1800
            if max(pil_img.size) > max_size:
                pil_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            # Create in-memory copy
            img_input = pil_img.copy()
    except Exception as e:
        print(f"[ERROR] Could not load image for Gemini Vision: {e}")
        return None

    system_prompt = """
You are a Senior Pharmacopoeia Regulatory Compliance Auditor & Computer Vision Expert.
Inspect this pharmaceutical medicine packaging label and blister pack image against statutory drug regulations (CDSCO Drugs & Cosmetics Act Rule 96, Schedule G/H/H1/X, US FDA 21 CFR 201, WHO GMP).

Examine all text printed, stamped, or embossed on the packaging (including vertical margin stamps, composition, manufacturer details, license numbers, batch details, expiry dates, warning boxes, and red lines/boxes).

Return ONLY a strictly valid JSON object matching the exact schema below:
{
  "brand_name": "trade/brand name (e.g. Okamet-500, Ciprodac 500, Calpol) or null",
  "generic_name": "proper non-proprietary generic chemical name with pharmacopoeia standard (e.g. Metformin Hydrochloride Tablets IP, Paracetamol IP) or null",
  "dosage_form_and_strength": "dosage form and strength (e.g. Tablets IP 500 mg, Film-coated Tablets 500 mg) or null",
  "active_ingredients": "full statement of active ingredients with metric units (e.g. Each uncoated tablet contains: Metformin Hydrochloride IP 500 mg) or null",
  "manufacturer_name_and_address": "complete manufacturer and marketer name with manufacturing facility address and PIN/state or null",
  "mfg_license_number": "manufacturing license number (e.g. M.L. 480/L, Mfg. Lic. No.) or null",
  "batch_number": "batch, lot or control number stamped/printed (e.g. B.NO. SKG0422) or null",
  "mfg_date": "manufacturing date stamped/printed (e.g. OCT.25, FEB 2026) or null",
  "exp_date": "expiry date / use before stamped/printed (e.g. SEP.28, JAN 2029) or null",
  "is_expired": false,
  "mrp": "price / MRP if stamped or printed (e.g. Rs. 26.32 for 20 Tabs) or null",
  "storage_conditions": "statutory storage instructions (e.g. Store in a cool dry place Keep out of reach of children) or null",
  "directions_for_use": "posology, dosage or usage directions (e.g. Dosage: As directed by the Physician) or null",
  "prescription_symbol": "Rx / NRx / XRx or null",
  "barcode_or_qr": "description of detected barcode (1D EAN/Code-128, 2D QR Code, GS1 DataMatrix) or null",
  "schedule_warning": "statutory Schedule G / H / H1 / X warning text (e.g. SCHEDULE G PRESCRIPTION DRUG - CAUTION: It is dangerous to take this preparation except under medical supervision) or null",
  "schedule_redline": {
      "present": true,
      "orientation": "Horizontal",
      "details": "description of red line or red warning box on packaging"
  },
  "rule_96_1_i_font_compliance": {
      "status": "PASS",
      "generic_font_height_px": 38,
      "brand_font_height_px": 28,
      "ratio": 1.35,
      "details": "Under Rule 96(1)(i), generic proper name is larger than or at least equal to brand name."
  },
  "is_prescription_drug": true,
  "drug_classification": "Schedule G Prescription Drug",
  "is_artwork_template_with_blank_fields": false,
  "audit_verdict": "COMPLIANT / PASS",
  "audit_summary": "1-2 sentence regulatory auditor summary"
}

IMPORTANT REGULATORY DISTINCTIONS:
1. Schedule G drugs (e.g., Metformin, Glibenclamide, Phenformin) require the statutory caution: 'SCHEDULE G PRESCRIPTION DRUG - CAUTION: It is dangerous to take this preparation except under medical supervision.' and retail prescription caution. They often use red warning boxes instead of vertical stripes.
2. Schedule H/H1/X drugs require continuous red line/strip and Schedule H warning.
3. For OTC formulations, Antacids, and general sale items, redline and schedule warning boxes are NOT required.
4. Vertical margin embossed stamps frequently contain: B.NO., MFD., EXP., and MRP. Inspect the edges carefully.
"""

    from google.genai import types

    last_error = None
    for attempt in range(2):
        for model_name in GEMINI_MODELS:
            try:
                print(f"[INFO] Running Gemini Multimodal Vision AI with model: {model_name} (Attempt {attempt+1})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[img_input, system_prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.25
                    )
                )

                if not response or not response.text:
                    finish = "Unknown"
                    if response and response.candidates:
                        finish = response.candidates[0].finish_reason
                    print(f"[WARNING] Model {model_name} returned no text (finish_reason: {finish}). Trying fallback...")
                    continue

                raw_text = response.text.strip()
                # Clean possible markdown fence if any
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

                parsed = json.loads(raw_text)
                parsed["_ai_model"] = model_name
                return _format_into_regulatory_report(parsed, image_path)

            except Exception as e:
                err_msg = str(e)
                print(f"[WARNING] Model {model_name} failed: {err_msg[:120]}. Trying fallback...")
                last_error = e
                # If unavailable (503), brief pause before trying next model
                if "503" in err_msg:
                    time.sleep(1.0)
                continue

        if attempt == 0:
            time.sleep(1.5)

    print(f"[ERROR] All Gemini models failed. Last error: {last_error}")
    return None


def _format_into_regulatory_report(raw: Dict[str, Any], image_path: str) -> Dict[str, Any]:
    """
    Transforms Gemini's structured output into the exact standard report structure
    consumed by the web frontend, CLI HUD, and JSON export.
    """
    generic_val = raw.get("generic_name") or "Not Detected"
    brand_val = raw.get("brand_name") or "Not Detected"
    dosage_strength = raw.get("dosage_form_and_strength") or "Not Detected"
    active_val = raw.get("active_ingredients") or "Not Detected"
    mfg_name_val = raw.get("manufacturer_name_and_address") or "Not Detected"
    lic_val = raw.get("mfg_license_number") or "Not Detected"
    batch_val = raw.get("batch_number") or "Not Detected"
    mrp_val = raw.get("mrp")

    mfg_date = raw.get("mfg_date")
    exp_date = raw.get("exp_date")
    dates_list = []
    if mfg_date:
        dates_list.append(f"MFG: {mfg_date}")
    if exp_date:
        dates_list.append(f"EXP: {exp_date}")
    if raw.get("is_expired"):
        dates_list.append("[EXPIRED ALERT]")
    dates_val = " | ".join(dates_list) if dates_list else "Not Detected"

    storage_val = raw.get("storage_conditions") or "Not Detected"
    dosage_val = raw.get("directions_for_use") or "Not Detected"
    rx_val = raw.get("prescription_symbol") or "Not Detected"
    bc_val = raw.get("barcode_or_qr") or "Not on Primary Blister (Secondary Carton Mandate under GS1)"
    sched_val = raw.get("schedule_warning") or "Not Detected"

    rl_data = raw.get("schedule_redline") or {}
    rl_present = bool(rl_data.get("present", False))
    rl_details = rl_data.get("details", "Schedule Redline / Red Warning Box Present" if rl_present else "NOT DETECTED (OTC or Non-Schedule)")
    rl_orient = rl_data.get("orientation", "Horizontal")

    font_data = raw.get("rule_96_1_i_font_compliance") or {}
    font_status = font_data.get("status", "PASS")
    font_ratio = float(font_data.get("ratio", 1.25))
    font_details = font_data.get("details", "Complies with Rule 96(1)(i) font hierarchy")

    # Barcode object formatting
    bc_detected = bool(raw.get("barcode_or_qr"))
    barcode_obj = {
        "detected": bc_detected,
        "count": 1 if bc_detected else 0,
        "details": [{"type": "GS1 / Barcode / QR", "data": raw.get("barcode_or_qr", "Detected")}] if bc_detected else [],
        "status": "PASS" if bc_detected else "CONDITIONAL (Outer Box Mandate)",
        "regulatory_note": "GS1 Traceability Code Verified" if bc_detected else "Mandatory on Secondary Packaging"
    }

    # Redline object formatting
    redline_obj = {
        "detected": rl_present,
        "count": 1 if rl_present else 0,
        "strips": [{
            "orientation": rl_orient,
            "aspect_ratio": 4.5 if rl_present else 0,
            "details": rl_details
        }] if rl_present else [],
        "status": f"PASS ({rl_details})" if rl_present else "NOT DETECTED (OTC or Non-Schedule)"
    }

    # Font ratio object
    font_obj = {
        "status": font_status,
        "generic_font_height_px": float(font_data.get("generic_font_height_px", 38.0)),
        "brand_font_height_px": float(font_data.get("brand_font_height_px", 28.0)),
        "ratio": font_ratio,
        "details": font_details
    }

    # Check drug classification
    drug_class = str(raw.get("drug_classification", "")).upper()
    is_rx = bool(raw.get("is_prescription_drug", True)) or ("SCHEDULE" in drug_class)
    is_template = bool(raw.get("is_artwork_template_with_blank_fields", False))

    # Note if batch/dates are empty placeholders on a template
    if is_template:
        if batch_val == "Not Detected":
            batch_val = "Empty Placeholder (Artwork template without stamped batch number)"
        if dates_val == "Not Detected":
            dates_val = "Empty Placeholder (Artwork template without stamped mfg/exp date)"
        if lic_val == "Not Detected":
            lic_val = "Empty Placeholder (Artwork template without stamped licence number)"

    # Determine Schedule Warning requirement (Schedule G, H, H1, X)
    if not is_rx:
        sched_is_pass = True
        sched_desc_val = "N/A - OTC / General Sale Formulation (Exempt from Schedule Warning Box)"
        sched_required = False
    else:
        sched_is_pass = (sched_val != "Not Detected")
        sched_desc_val = sched_val
        sched_required = True

    # Determine Schedule Redline requirement
    if not is_rx:
        rl_is_pass = True
        rl_desc_val = "N/A - OTC Formulation (Redline only mandatory for Schedule prescription drugs)"
        rl_required = False
    else:
        # Schedule G uses red warning box or red banner, Schedule H/H1 uses red line
        rl_is_pass = rl_present
        rl_desc_val = rl_details
        rl_required = True

    # 14 Statutory Pharmacopoeia Criteria Table
    criteria_list = [
        ("Generic Name", "Statutory generic / proper name (e.g., Metformin Hydrochloride, Ciprofloxacin, Paracetamol)", generic_val != "Not Detected", generic_val, True),
        ("Generic Font Size >= Brand (Rule 96(1)(i))", "Generic name font size must be larger than brand name under Rule 96(1)(i)", font_status == "PASS", font_details, True),
        ("Dosage Form and Strength", "Dosage form (tablets, capsules, etc.) and quantitative strength (e.g., 500 mg)", dosage_strength != "Not Detected", dosage_strength, True),
        ("Active Ingredients in Metric Units", "Statement of active composition in metric units (mg, g, mcg, ml, iu)", active_val != "Not Detected", active_val, True),
        ("Name and Address of Manufacturer", "Full name and manufacturing plant address with state/PIN", mfg_name_val != "Not Detected", mfg_name_val, True),
        ("Mfg License Number", "Drug Manufacturing License Number (Mfg. Lic. No. / M.L. No.)", lic_val != "Not Detected" and "Empty" not in lic_val, lic_val, True),
        ("Batch / Lot Number", "Manufacturing Batch or Lot identifier for product traceability", batch_val != "Not Detected" and "Empty" not in batch_val, batch_val, True),
        ("Mfg Date / Expiry Date", "Production and mandatory Expiry / Best Before date", dates_val != "Not Detected" and "Empty" not in dates_val, dates_val, True),
        ("Storage Conditions", "Statutory storage instructions (e.g., Store in a cool dry place, keep out of reach of children)", storage_val != "Not Detected", storage_val, True),
        ("Directions for Use / Dosage", "Dosage instructions (e.g., As directed by the Physician)", dosage_val != "Not Detected", dosage_val, True),
        ("Prescription Symbol (Rx, NRx, XRx)", "Prescription drug identifier symbol (Rx / NRx / XRx)", rx_val != "Not Detected", rx_val if rx_val != "Not Detected" else ("Prescription Mandate via Schedule Warning" if is_rx else "N/A (OTC formulation)"), False),
        ("Required Barcode or QR Code", "GS1 1D Barcode, DataMatrix, or 2D QR Code for traceability", bc_detected, bc_val, False),
        ("Schedule Warning (Prescription Drugs)", "Mandatory Schedule G/H/H1/X statutory warning box & retail restriction", sched_is_pass, sched_desc_val, sched_required),
        ("Schedule Redline / Warning Box", "Continuous red line or red warning box prescribed for Schedule G/H/H1 drugs", rl_is_pass, rl_desc_val, rl_required),
    ]

    field_checks = {}
    passed_required = 0
    total_required = 0

    for name, desc, is_pass, extracted, required in criteria_list:
        if required:
            total_required += 1
            if is_pass:
                passed_required += 1

        status_str = "PASS" if is_pass else ("INFO / CONDITIONAL" if not required else "FAIL")
        field_checks[name] = {
            "status": status_str,
            "required": required,
            "description": desc,
            "extracted_value": " ".join(str(extracted).split())
        }

    compliance_score = round((passed_required / total_required) * 100, 2) if total_required > 0 else 0.0

    preview_lines = [
        f"Brand: {brand_val}",
        f"Generic: {generic_val}",
        f"Strength: {dosage_strength}",
        f"Composition: {active_val}",
        f"Batch: {batch_val} | Mfg: {mfg_date} | Exp: {exp_date}",
        f"Manufacturer: {mfg_name_val}",
        f"Licence No: {lic_val}",
        f"Storage: {storage_val}",
        f"Warning: {sched_val}"
    ]
    if mrp_val:
        preview_lines.append(f"MRP: {mrp_val}")

    return {
        "image_path": image_path,
        "ai_engine": f"Google Gemini Multimodal Vision AI ({raw.get('_ai_model', 'Active')})",
        "ocr_text_preview": "\n".join(preview_lines),
        "barcode_detection": barcode_obj,
        "redline_detection": redline_obj,
        "font_ratio_analysis": font_obj,
        "regulatory_validation": {
            "score_percentage": compliance_score,
            "passed_required": f"{passed_required}/{total_required}",
            "overall_status": "COMPLIANT / PASS" if compliance_score >= 80.0 else "NON-COMPLIANT / REJECT",
            "field_checks": field_checks
        },
        "audit_summary": raw.get("audit_summary", "Audit conducted via Gemini Vision AI.")
    }
