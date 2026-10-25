# 💊 Pharmaceutical Medicine Label Validation & Scanning System
### Comprehensive Project Documentation & Production Live Hosting Manual

---

## 📑 Table of Contents
1. [Executive Summary: What is this Project?](#1-executive-summary-what-is-this-project)
2. [Why This Project Exists: Problem Statement & Regulatory Context](#2-why-this-project-exists-problem-statement--regulatory-context)
3. [Items & Technologies Used in this Project (Tech Stack Breakdown)](#3-items--technologies-used-in-this-project-tech-stack-breakdown)
4. [System Architecture & Processing Pipeline](#4-system-architecture--processing-pipeline)
5. [The 14 Statutory Pharmacopoeia Validation Criteria](#5-the-14-statutory-pharmacopoeia-validation-criteria)
6. [Repository & Directory Structure](#6-repository--directory-structure)
7. [System Configuration & Environment Variables](#7-system-configuration--environment-variables)
8. [Step-by-Step Production Hosting Guide (Live Deployment)](#8-step-by-step-production-hosting-guide-live-deployment)
   - [Option 1: Deploy on Render.com (Recommended Free Cloud Hosting)](#option-1-deploy-on-rendercom-recommended-free-cloud-hosting)
   - [Option 2: Deploy on Railway.app (Zero-Config Docker Hosting)](#option-2-deploy-on-railwayapp-zero-config-docker-hosting)
   - [Option 3: Deploy on Ubuntu VPS / AWS EC2 (Nginx + Gunicorn + Systemd)](#option-3-deploy-on-ubuntu-vps--aws-ec2-nginx--gunicorn--systemd)
   - [Option 4: Run Locally or in Cloud via Docker](#option-4-run-locally-or-in-cloud-via-docker)
   - [Option 5: Host on Windows Server (Waitress WSGI)](#option-5-host-on-windows-server-waitress-wsgi)
9. [REST API Documentation & Endpoints](#9-rest-api-documentation--endpoints)
10. [Troubleshooting & Frequently Asked Questions (FAQ)](#10-troubleshooting--frequently-asked-questions-faq)

---

## 1. Executive Summary: What is this Project?

The **Pharmaceutical Medicine Label Validation & Scanning System** is an AI- and Computer Vision-driven quality assurance and regulatory inspection platform. 

It automatically inspects images of pharmaceutical medicine packaging (blister packs, strips, bottles, cartons) captured via camera, smartphone, or scanner, and checks whether the packaging complies with strict national and international drug labeling laws (**CDSCO Drugs & Cosmetics Act Rule 96**, **US FDA 21 CFR Part 201**, and **WHO Good Manufacturing Practices**).

### What the System Delivers:
1. **Automated Optical Character Recognition (OCR)**: Extracts micro-printed statutory text from foil and glossy packaging despite glare, angle, or perspective distortion.
2. **Mandatory Redline Detection**: Employs HSV color segmentation and morphological geometry analysis to detect prescription Schedule H/H1 red cautionary strips.
3. **Traceability Barcode & QR Code Decoding**: Extracts GS1 1D/2D barcodes for anti-counterfeit batch verification.
4. **14 Statutory Criteria Verification Engine**: Assesses critical parameters such as Generic Name, Font Ratio (Rule 96(1)(i)), Active Composition, Expiry Date, License Number, and Schedule Warnings.
5. **Interactive Inspection HUD & Visual Annotation**: Generates a bounding-box visual report (`annotated_result.jpg`) highlighting detected parameters, alongside a structured JSON audit trail.
6. **Modern Web Dashboard & REST API**: Allows hospital pharmacists, drug inspectors, and pharmaceutical quality control teams to drag and drop packaging photos or trigger live camera captures.

---

## 2. Why This Project Exists: Problem Statement & Regulatory Context

### The Real-World Problem:
- **Counterfeit & Substandard Drugs**: Counterfeit and mislabeled drugs account for over $200B in illicit trade globally, endangering millions of lives.
- **Fatal Dispensing Errors**: Look-alike packaging or missing prescription warnings lead to medication mix-ups in busy pharmacies and hospitals.
- **Manual Inspection Bottlenecks**: Drug regulatory inspectors and manufacturing QA officers manually inspect hundreds of thousands of batches, making human fatigue and oversights common.

### Statutory Laws Enforced by the System:
- **CDSCO Drugs and Cosmetics Act (Rule 96)**: Dictates that the generic (proper) name of a medicine must appear conspicuously and be at least as large (or 2 font sizes larger) than the commercial brand name.
- **Schedule H / H1 / X Warnings**: Prescription drugs must display a prominent red vertical/horizontal strip and statutory warning: *"To be sold by retail on the prescription of a Registered Medical Practitioner only"*.
- **Traceability Mandate**: Batch numbers, manufacturing/expiry dates, manufacturer address, and GS1 Barcodes/QR codes are mandatory for supply chain traceability.

---

## 3. Items & Technologies Used in this Project (Tech Stack Breakdown)

Below is an exhaustive breakdown of all software items, libraries, and frameworks employed:

| Category | Technology / Item | Purpose & Role in the Project |
| :--- | :--- | :--- |
| **Backend Language** | **Python 3.10+** | Core programming language executing OCR, image transformations, and server routing. |
| **Web Framework** | **Flask 3.0+** | Provides lightweight REST API endpoints (`/api/scan`, `/health`) and serves the frontend dashboard. |
| **Production WSGI (Linux)** | **Gunicorn 21.2+** | High-performance multi-process WSGI HTTP server for production cloud hosting (Render, Railway, AWS). |
| **Production WSGI (Windows)** | **Waitress 2.1+** | Multi-threaded production WSGI server for Windows production environments. |
| **Computer Vision** | **OpenCV (`cv2`) 4.8+** | Implements CLAHE illumination normalization, Bilateral noise filtering, Otsu binarization, HSV red color masking, contour detection, and visual bounding box annotations. |
| **OCR Engine** | **Tesseract OCR (Google / UB-Mannheim)** | State-of-the-art LSTM (Long Short-Term Memory) neural network character recognition engine (Page Segmentation Mode 6, OEM 3). |
| **OCR Python Wrapper** | **Pytesseract 0.3.10+** | Python interface to execute Tesseract OCR and extract text and word bounding box coordinates. |
| **Barcode & QR Decoding** | **Pyzbar 0.1.9+ (`libzbar`)** | Decodes 1D barcodes (EAN-13, Code 128) and 2D GS1 DataMatrix / QR codes from packaging. |
| **Array & Matrix Math** | **NumPy 1.23+** | Performs fast matrix math for image masks, threshold slicing, and pixel manipulation. |
| **Image Processing** | **Pillow (PIL) 9.5+** | Handles image reading, color space conversion, and synthetic sample packaging rendering. |
| **Frontend Architecture** | **HTML5 & Vanilla CSS3** | Modern Glassmorphic Dark UI design, CSS Flexbox/Grid, glowing status badges, and micro-animations. |
| **Frontend Scripting** | **Vanilla JavaScript (ES6+)** | Handles drag-and-drop file upload, live webcam streaming, scanning progress bar animations, and JSON modal viewer without heavy framework overhead. |
| **Containerization** | **Docker & Dockerfile** | Packages Python, Debian runtime, Tesseract OCR binaries, and `libzbar0` into a self-contained production image. |
| **Cloud Blueprint** | **render.yaml / Procfile** | Infrastructure-as-code files enabling 1-click cloud deployment. |

---

## 4. System Architecture & Processing Pipeline

```
[ Packaging Photo / Blister Scan ]
               │
               ▼
   [ 1. Auto-Crop & Letterbox Removal ]
               │
       ┌───────┴───────────────────────────────┐
       ▼                                       ▼
[ 2. OCR Preprocessing ]             [ 3. Barcode & QR Decoding ]
  - Grayscale Conversion                (Pyzbar / libzbar)
  - CLAHE Lighting Equalization         - EAN-13, Code 128
  - Bilateral Edge Filter               - GS1 QR / DataMatrix
  - Otsu Binarization                          │
       │                                       │
       ▼                                       │
[ 4. Tesseract OCR Engine (PSM 6) ]            │
  - Text Stream Extraction                     │
  - Character Bounding Boxes                   │
       │                                       │
       ▼                                       │
[ 5. Regulatory Verification Engine ]          │
  - 14 Pharmacopoeia Checks (Regex)            │
  - Font Size Ratio (Rule 96(1)(i))            │
       │                                       │
       ├───────────────────────────────────────┘
       ▼
[ 6. Schedule Redline Detection (OpenCV) ]
  - HSV Color Filtering (0°-10° & 170°-180°)
  - Morphological Rectangular Kernels
  - Aspect Ratio Geometry Filter (>= 3.5)
       │
       ▼
[ 7. Compliance Aggregation & Scoring ]
       │
       ├──► [ Annotated Inspection Image (annotated_result.jpg) ]
       ├──► [ Structured Audit Report (validation_report.json) ]
       └──► [ Web Dashboard & REST API Output ]
```

---

## 5. The 14 Statutory Pharmacopoeia Validation Criteria

Every medicine label uploaded is evaluated against these 14 statutory parameters:

| # | Parameter | Statutory Basis | Verification Logic & How It Works |
| :---: | :--- | :--- | :--- |
| **1** | **Generic Name (INN / Proper Name)** | CDSCO Rule 96(1) | Detects official pharmacopeial designations (`IP`, `BP`, `USP`) and active therapeutic chemical compounds (e.g. *Ciprofloxacin*). |
| **2** | **Generic Font Size >= Brand Name** | Rule 96(1)(i) | Compares character bounding box pixel heights between Brand and Generic text to ensure the generic name is prominent. |
| **3** | **Dosage Form & Strength** | FDA 21 CFR 201.10 | Identifies dosage forms (`Tablets`, `Capsules`, `Syrup`, `Injection`) and concentration metrics (`500 mg`, `10 ml`, `w/v`). |
| **4** | **Active Ingredients in Metric Units** | WHO GMP / Pharmacopoeia | Detects composition statements (`Each film-coated tablet contains...`) and verified metric units (`mg`, `mcg`, `g`, `iu`). |
| **5** | **Manufacturer Name & Address** | Legal Metrology & Drugs Act | Extracts `"Manufactured by:"` / `"Mfd by:"` followed by facility location and postal code. |
| **6** | **Manufacturing License Number** | Statutory Licensing | Recognizes `"Mfg. Lic. No."`, `"M.L. No."`, or `"Licence No."` required by state drug authorities. |
| **7** | **Batch / Lot Number** | Traceability Mandate | Identifies batch identifiers (`"B.No."`, `"Batch No."`, `"Lot No."`), including side-strip printed batch codes. |
| **8** | **Mfg Date & Expiry Date** | Patient Safety Mandate | Verifies shelf life dates (`"Mfg Date"`, `"Exp Date"`, `"Expiry"`) formatted in month/year. |
| **9** | **Storage Conditions** | Stability & Efficacy | Verifies temperature and humidity warnings (`"Store protected from light and moisture"`, `"Store below 25°C"`). |
| **10** | **Directions for Use / Dosage** | Posology Guidelines | Confirms prescription posology instruction: `"Dosage: As directed by the Physician"`. |
| **11** | **Prescription Symbol (Rx, NRx, XRx)** | Schedule H / Narcotics Act | Checks for mandatory Rx, NRx (narcotic), or XRx (psychotropic) symbols in the header. |
| **12** | **GS1 Barcode or 2D QR Code** | Anti-Counterfeiting Rule | Verifies presence of readable 1D EAN/UPC barcode or 2D GS1 DataMatrix code. |
| **13** | **Schedule Statutory Warning Box** | Schedule H / H1 / G / X | Validates the boxed caution: `"SCHEDULE H PRESCRIPTION DRUG - CAUTION: Not to be sold by retail without prescription..."`. |
| **14** | **Prescription Redline** | Schedule H Prominent Strip | Detects continuous red bar across blister/carton using dual-band HSV segmentation and aspect ratio checking ($\ge 3.5$). |

---

## 6. Repository & Directory Structure

```
d:\fami\
│
├── app.py                     # Core validation engine (OCR, Redline, Regex checks, sample generator)
├── server.py                  # Flask web server & REST API endpoints (/api/scan, /health)
├── wsgi.py                    # Standard WSGI entrypoint for Gunicorn & Waitress production servers
├── requirements.txt           # Python package dependencies (Flask, OpenCV, Pytesseract, Gunicorn, etc.)
├── Dockerfile                 # Production Docker container definition with Tesseract & libzbar
├── .dockerignore              # Prevents unnecessary files from bloating the Docker image
├── Procfile                   # Cloud process execution command for Render / Railway / Heroku
├── render.yaml                # Render Blueprint infrastructure-as-code specification
│
├── run.bat                    # Windows 1-click CLI quick scan launcher
├── run_web.bat                # Windows 1-click Flask dev server launcher
├── run_production.bat         # Windows 1-click Waitress production WSGI launcher
│
├── static/
│   ├── css/
│   │   └── style.css          # Modern Glassmorphic Dark UI styles
│   ├── js/
│   │   └── main.js            # Frontend JavaScript (Drag-and-Drop, Camera capture, Scanning HUD)
│   └── uploads/               # Storage directory for uploaded images and generated annotations
│
├── templates/
│   └── index.html             # Main web dashboard interface
│
├── README.md                  # Project overview & presentation guide
└── PROJECT_DOCUMENTATION.md   # This comprehensive master documentation manual
```

---

## 7. System Configuration & Environment Variables

The application can be configured via environment variables or `.env` files:

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PORT` | `5000` | Network port on which the web server listens. Cloud providers (Render, Railway, Heroku) inject this automatically. |
| `HOST` | `0.0.0.0` | IP binding. `0.0.0.0` allows external cloud traffic; `127.0.0.1` is for localhost-only testing. |
| `TESSERACT_PATH` / `TESSERACT_CMD` | *Auto-detected* | Custom absolute path to the Tesseract binary (e.g. `/usr/bin/tesseract` on Linux or `C:\Program Files\Tesseract-OCR\tesseract.exe` on Windows). |
| `UPLOAD_FOLDER` | `static/uploads` | Path where input packaging images and annotated outputs are saved. |
| `MAX_CONTENT_LENGTH` | `16777216` (16 MB) | Maximum permitted file upload size to prevent denial-of-service from massive images. |

### System Runtime Dependencies:
- **Tesseract OCR**:
  - Ubuntu/Debian: `sudo apt-get install tesseract-ocr tesseract-ocr-eng`
  - Windows: UB-Mannheim Tesseract installer installed to `C:\Program Files\Tesseract-OCR`.
- **ZBar Barcode Library**:
  - Ubuntu/Debian: `sudo apt-get install libzbar0`
  - Windows: Visual C++ 2015-2022 x64 Redistributable (includes `libzbar-64.dll`).
- **OpenCV Runtime Libraries (Headless Linux)**:
  - Ubuntu/Debian: `sudo apt-get install libgl1 libglib2.0-0`

---

## 8. Step-by-Step Production Hosting Guide (Live Deployment)

Because this application relies on C-libraries (`tesseract-ocr` and `libzbar0`), **the cleanest, most reliable production deployment method is Docker or a platform that supports Dockerfiles**.

Below are the 5 deployment options, ranked by ease of setup:

---

### Option 1: Deploy on Render.com (Recommended Free Cloud Hosting)

Render provides free hosting with native Docker support. Your app will receive a free public SSL URL (e.g. `https://pharma-label-scanner.onrender.com`).

#### Step-by-Step Instructions:
1. **Push your code to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Production ready pharma label scanner"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/pharma-label-scanner.git
   git push -u origin main
   ```
2. **Log in to [Render.com](https://render.com/)**:
   - Sign in with your GitHub account.
3. **Create a New Web Service**:
   - Click **New +** -> **Web Service**.
   - Select **Build and deploy from a Git repository**.
   - Connect your GitHub repository `pharma-label-scanner`.
4. **Configure Settings**:
   - **Name**: `pharma-label-scanner`
   - **Region**: Choose the closest region (e.g., Frankfurt or Oregon).
   - **Environment**: Select **Docker** (Render will automatically detect the [Dockerfile](file:///d:/fami/Dockerfile)).
   - **Plan**: Select **Free**.
5. **Deploy**:
   - Click **Create Web Service**.
   - Render will build the container, install Tesseract & ZBar, and start Gunicorn automatically.
   - Once build logs display `PHARMA LABEL SCANNER WEB SERVER READY`, your live URL is active!

---

### Option 2: Deploy on Railway.app (Zero-Config Docker Hosting)

Railway is an exceptionally fast cloud host that automatically detects Dockerfiles.

#### Step-by-Step Instructions:
1. Visit [Railway.app](https://railway.app/) and sign in with GitHub.
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select your repository.
4. Railway automatically detects the [Dockerfile](file:///d:/fami/Dockerfile) and runs:
   ```bash
   gunicorn --bind 0.0.0.0:$PORT wsgi:app
   ```
5. In project **Settings** -> **Networking**, click **Generate Domain**.
6. Your live public HTTPS URL will be generated immediately.

---

### Option 3: Deploy on Ubuntu VPS / AWS EC2 (Nginx + Gunicorn + Systemd)

If you are hosting on your own Linux server (AWS EC2, DigitalOcean Droplet, Linode, or Hetzner):

#### 1. Connect and install OS dependencies:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git tesseract-ocr tesseract-ocr-eng libzbar0 libgl1 libglib2.0-0 nginx
```

#### 2. Clone the project and create virtual environment:
```bash
cd /var/www
sudo git clone https://github.com/YOUR_USERNAME/pharma-label-scanner.git
cd pharma-label-scanner
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
mkdir -p static/uploads
```

#### 3. Create a Systemd Service for Gunicorn:
```bash
sudo nano /etc/systemd/system/pharma_scanner.service
```
Paste the following:
```ini
[Unit]
Description=Pharmaceutical Medicine Label Scanner WSGI Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/pharma-label-scanner
Environment="PATH=/var/www/pharma-label-scanner/venv/bin"
ExecStart=/var/www/pharma-label-scanner/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo chown -R www-data:www-data /var/www/pharma-label-scanner
sudo systemctl daemon-reload
sudo systemctl start pharma_scanner
sudo systemctl enable pharma_scanner
```

#### 4. Configure Nginx Reverse Proxy:
```bash
sudo nano /etc/nginx/sites-available/pharma_scanner
```
Paste the following configuration:
```nginx
server {
    listen 80;
    server_name your_domain.com www.your_domain.com;
    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/pharma-label-scanner/static/;
        expires 30d;
    }
}
```
Enable site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/pharma_scanner /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 5. Install Free SSL with Let's Encrypt Certbot:
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your_domain.com -d www.your_domain.com
```

---

### Option 4: Run Locally or in Cloud via Docker

To run the containerized application on any computer or server with Docker installed:

1. **Build the Docker Image**:
   ```bash
   docker build -t pharma-validator:latest .
   ```
2. **Run the Container**:
   ```bash
   docker run -d --name pharma_app -p 5000:5000 pharma-validator:latest
   ```
3. Open your browser at **`http://localhost:5000`**.

To stop and remove:
```bash
docker stop pharma_app && docker rm pharma_app
```

---

### Option 5: Host on Windows Server (Waitress WSGI)

For production deployment on Windows Server without Docker:

1. Install Python 3.10+ and add it to PATH.
2. Install Tesseract OCR for Windows to `C:\Program Files\Tesseract-OCR`.
3. Install Visual C++ 2015-2022 Redistributable (x64).
4. Run:
   ```cmd
   pip install -r requirements.txt
   ```
5. Double click **`run_production.bat`** (or launch via PowerShell):
   ```cmd
   python -m waitress --listen=0.0.0.0:5000 wsgi:app
   ```
This launches a robust multi-threaded WSGI server ready for enterprise local network or domain traffic.

---

## 9. REST API Documentation & Endpoints

### 1. Health Check Endpoint
- **URL**: `/health`
- **Method**: `GET`
- **Response**:
```json
{
  "status": "ok",
  "service": "Pharma Label Scanner",
  "version": "1.0.0"
}
```

---

### 2. Label Scan Endpoint
- **URL**: `/api/scan`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Form Parameters**:
  - `image` *(file, optional if `is_sample=true`)*: Image file (PNG, JPG, WEBP, BMP, TIFF) up to 16MB.
  - `is_sample` *(string, optional)*: Set to `"true"` to generate and scan a synthetic compliant test label.

#### Example Success Response:
```json
{
  "success": true,
  "original_image_url": "/static/uploads/upload_a1b2c3d4.png",
  "annotated_image_url": "/static/uploads/annotated_a1b2c3d4.jpg",
  "report": {
    "summary": {
      "overall_status": "COMPLIANT",
      "compliance_score_percent": 100.0,
      "passed_rules": 14,
      "total_rules": 14
    },
    "barcode_check": {
      "status": "PASS",
      "count": 1,
      "items": [
        {
          "type": "QRCODE",
          "data": "GS1:010890123456789010B1049211726053121987654321"
        }
      ]
    },
    "redline_check": {
      "status": "PASS",
      "line_count": 1,
      "strips": [
        {
          "aspect_ratio": 34.2,
          "orientation": "HORIZONTAL"
        }
      ]
    },
    "criteria_results": [
      {
        "id": 1,
        "name": "Generic Name (Proper Name / INN)",
        "status": "PASS",
        "matched_text": "Ciprofloxacin Tablets IP"
      },
      {
        "id": 2,
        "name": "Generic Font Size >= Brand Name",
        "status": "PASS",
        "matched_text": "Generic Height: 28px >= Brand Height: 26px"
      }
    ]
  }
}
```

---

## 10. Troubleshooting & Frequently Asked Questions (FAQ)

### Q1: "Tesseract-OCR executable not found"
- **Cause**: Tesseract OCR engine binary is not installed on the host OS.
- **Fix**:
  - **Windows**: Install UB-Mannheim Tesseract OCR installer into `C:\Program Files\Tesseract-OCR\`.
  - **Linux / Docker**: Run `apt-get install -y tesseract-ocr tesseract-ocr-eng`.
  - **Custom Path**: Set environment variable `TESSERACT_PATH=/custom/path/to/tesseract`.

### Q2: "Unable to find zbar shared library (`libzbar-64.dll` or `libzbar.so`)"
- **Cause**: Pyzbar requires the underlying C library.
- **Fix**:
  - **Windows**: Install [Visual C++ 2015-2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe).
  - **Linux**: Run `sudo apt-get install libzbar0`.

### Q3: "Camera capture from tablet or phone appears sideways or blurry"
- **Answer**: The application includes an **Automatic EXIF Orientation Normalizer** and **Edge Auto-Cropper** (`autocrop_borders` in `app.py`) that strips away black borders and re-aligns smartphone photographs prior to OCR processing.

### Q4: "How do I increase the maximum upload limit?"
- Edit line 27 of [server.py](file:///d:/fami/server.py):
  ```python
  app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # Increases to 32 MB
  ```

---

*Authored for Pharmaceutical Regulatory Inspection & Academic Research.*
