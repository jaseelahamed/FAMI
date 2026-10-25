# ==============================================================================
# PHARMACEUTICAL MEDICINE LABEL VALIDATOR - DOCKERFILE (PRODUCTION)
# ==============================================================================
FROM python:3.10-slim

# Prevent Python from writing .pyc files & enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    HOST=0.0.0.0

# Install Linux system dependencies:
# - tesseract-ocr & language packs: OCR character recognition engine
# - libzbar0: Barcode & QR code scanning C library (pyzbar)
# - libgl1 & libglib2.0-0: OpenCV graphics runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libzbar0 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Copy dependency definition first for optimal layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire project code into the container
COPY . .

# Ensure upload directory exists with proper permissions
RUN mkdir -p static/uploads

# Expose port (default 5000)
EXPOSE 5000

# Start with Gunicorn production WSGI server
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 server:app
