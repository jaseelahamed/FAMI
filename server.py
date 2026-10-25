"""
================================================================================
PHARMACEUTICAL MEDICINE LABEL VALIDATOR - WEB SERVER (FLASK)
================================================================================
Provides a modern REST API & Web Dashboard to upload, scan, and inspect
medicine packaging labels with AI, OCR, Barcode, and Redline verification.
================================================================================
"""

import os
import sys
import uuid
import json
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# Ensure d:\fami is in path and import validator
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import MedicineLabelValidator, configure_tesseract, generate_sample_medicine_label

# Initialize Flask
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max image upload
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
configure_tesseract()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "Pharma Label Scanner", "version": "1.0.0"}), 200


@app.route("/api/scan", methods=["POST"])
def scan_label():
    try:
        # Dynamically reload app module to ensure latest validation rules are applied
        import importlib
        import app as app_module
        importlib.reload(app_module)
        ValidatorClass = app_module.MedicineLabelValidator
        sample_generator = app_module.generate_sample_medicine_label

        # Check if sample button was clicked
        is_sample = request.form.get("is_sample") == "true"

        if is_sample:
            unique_id = str(uuid.uuid4())[:8]
            input_filename = f"sample_{unique_id}.png"
            input_path = os.path.join(app.config["UPLOAD_FOLDER"], input_filename)
            sample_generator(input_path)
        else:
            if "image" not in request.files:
                return jsonify({"success": False, "error": "No image file provided"}), 400

            file = request.files["image"]
            if file.filename == "":
                return jsonify({"success": False, "error": "No file selected"}), 400

            if not allowed_file(file.filename):
                return jsonify({
                    "success": False,
                    "error": f"Invalid format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                }), 400

            unique_id = str(uuid.uuid4())[:8]
            ext = file.filename.rsplit(".", 1)[1].lower()
            input_filename = f"upload_{unique_id}.{ext}"
            input_path = os.path.join(app.config["UPLOAD_FOLDER"], input_filename)
            file.save(input_path)

        # Run validation pipeline
        validator = ValidatorClass(input_path)
        report = validator.run_full_pipeline()

        # Generate annotated visual output
        annotated_filename = f"annotated_{unique_id}.jpg"
        annotated_path = os.path.join(app.config["UPLOAD_FOLDER"], annotated_filename)
        validator.generate_annotated_output(annotated_path)

        return jsonify({
            "success": True,
            "original_image_url": f"/static/uploads/{input_filename}",
            "annotated_image_url": f"/static/uploads/{annotated_filename}",
            "report": report
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/static/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 70)
    print("  PHARMA LABEL SCANNER WEB SERVER READY")
    print(f"  Listening on: http://{host}:{port}")
    print("=" * 70 + "\n")
    app.run(host=host, port=port, debug=False)
