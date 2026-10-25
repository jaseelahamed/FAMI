/**
 * ==============================================================================
 * PHARMASCAN AI - CLIENT JAVASCRIPT CONTROLLER
 * ==============================================================================
 */

document.addEventListener("DOMContentLoaded", () => {
    // Elements
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const dropzonePrompt = document.getElementById("dropzonePrompt");
    const previewWrapper = document.getElementById("previewWrapper");
    const imagePreview = document.getElementById("imagePreview");
    const btnClearFile = document.getElementById("btnClearFile");

    const btnScan = document.getElementById("btnScan");
    const btnSample = document.getElementById("btnSample");

    const scanProgress = document.getElementById("scanProgress");
    const progressBarFill = document.getElementById("progressBarFill");
    const progressStatus = document.getElementById("progressStatus");

    const emptyState = document.getElementById("emptyState");
    const resultsContent = document.getElementById("resultsContent");
    const verdictPill = document.getElementById("verdictPill");
    const verdictText = document.getElementById("verdictText");

    const metricScore = document.getElementById("metricScore");
    const metricRatio = document.getElementById("metricRatio");
    const metricFont = document.getElementById("metricFont");
    const metricFontSub = document.getElementById("metricFontSub");
    const metricBarcode = document.getElementById("metricBarcode");
    const metricBarcodeSub = document.getElementById("metricBarcodeSub");
    const metricRedline = document.getElementById("metricRedline");
    const metricRedlineSub = document.getElementById("metricRedlineSub");

    const checklistContainer = document.getElementById("checklistContainer");
    const annotatedImage = document.getElementById("annotatedImage");
    const btnDownloadImage = document.getElementById("btnDownloadImage");
    const ocrTextBox = document.getElementById("ocrTextBox");
    const jsonTextBox = document.getElementById("jsonTextBox");
    const btnDownloadJson = document.getElementById("btnDownloadJson");
    const btnCopyOcr = document.getElementById("btnCopyOcr");

    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabPanes = document.querySelectorAll(".tab-pane");

    let selectedFile = null;
    let progressTimer = null;

    // --------------------------------------------------------------------------
    // Drag & Drop / File Selection
    // --------------------------------------------------------------------------
    dropzone.addEventListener("click", (e) => {
        if (e.target !== btnClearFile) {
            fileInput.click();
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.remove("dragover");
        });
    });

    dropzone.addEventListener("drop", (e) => {
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    function handleFileSelect(file) {
        if (!file.type.startsWith("image/")) {
            alert("Please select a valid image file (PNG, JPG, WEBP).");
            return;
        }

        selectedFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            imagePreview.src = e.target.result;
            dropzonePrompt.style.display = "none";
            previewWrapper.style.display = "block";
            btnScan.disabled = false;
        };
        reader.readAsDataURL(file);
    }

    btnClearFile.addEventListener("click", (e) => {
        e.stopPropagation();
        clearFileSelection();
    });

    function clearFileSelection() {
        selectedFile = null;
        fileInput.value = "";
        imagePreview.src = "";
        dropzonePrompt.style.display = "block";
        previewWrapper.style.display = "none";
        btnScan.disabled = true;
    }

    // --------------------------------------------------------------------------
    // Tab Navigation
    // --------------------------------------------------------------------------
    tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");

            tabButtons.forEach((b) => b.classList.remove("active"));
            tabPanes.forEach((p) => p.classList.remove("active"));

            btn.classList.add("active");
            document.getElementById(targetTab).classList.add("active");
        });
    });

    // --------------------------------------------------------------------------
    // Scanning API Trigger
    // --------------------------------------------------------------------------
    btnScan.addEventListener("click", () => {
        if (!selectedFile) return;
        const formData = new FormData();
        formData.append("image", selectedFile);
        performScan(formData);
    });

    btnSample.addEventListener("click", () => {
        const formData = new FormData();
        formData.append("is_sample", "true");
        performScan(formData);
    });

    function startProgressAnimation() {
        scanProgress.style.display = "block";
        progressBarFill.style.width = "0%";
        progressStatus.textContent = "Uploading image to server...";

        let percent = 5;
        const steps = [
            { threshold: 18, text: "Auto-Cropping Letterbox Margins & Enhancing Contrast..." },
            { threshold: 40, text: "Multi-Orientation OCR (0°, 90°, 270° Text Scanning)..." },
            { threshold: 65, text: "HSV Dual-Band Schedule Redline Detection..." },
            { threshold: 80, text: "Measuring Font Size Bounding Boxes (Rule 96(1)(i))..." },
            { threshold: 92, text: "Verifying 14 Pharmacopoeia Statutory Regulatory Criteria..." }
        ];

        let currentStep = 0;
        clearInterval(progressTimer);
        progressTimer = setInterval(() => {
            if (percent < 92) {
                percent += 3;
                progressBarFill.style.width = percent + "%";

                if (currentStep < steps.length && percent >= steps[currentStep].threshold) {
                    progressStatus.textContent = steps[currentStep].text;
                    currentStep++;
                }
            }
        }, 120);
    }

    function stopProgressAnimation() {
        clearInterval(progressTimer);
        progressBarFill.style.width = "100%";
        progressStatus.textContent = "Audit Completed!";
        setTimeout(() => {
            scanProgress.style.display = "none";
        }, 400);
    }

    async function performScan(formData) {
        btnScan.disabled = true;
        btnSample.disabled = true;
        startProgressAnimation();

        try {
            const response = await fetch("/api/scan", {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            if (!data.success) {
                alert("Inspection Error: " + (data.error || "Unknown server error"));
                return;
            }

            renderResults(data);

        } catch (error) {
            console.error("Scan request failed:", error);
            alert("Network error: Could not contact inspection server.");
        } finally {
            stopProgressAnimation();
            btnScan.disabled = !selectedFile;
            btnSample.disabled = false;
        }
    }

    // --------------------------------------------------------------------------
    // Render Inspection Results
    // --------------------------------------------------------------------------
    function renderResults(data) {
        const report = data.report;
        const val = report.regulatory_validation;
        const bc = report.barcode_detection;
        const rl = report.redline_detection;
        const fontData = report.font_ratio_analysis || {};

        emptyState.style.display = "none";
        resultsContent.style.display = "block";
        verdictPill.style.display = "inline-flex";

        // 1. Overall Score & Verdict
        const score = val.score_percentage;
        metricScore.textContent = score + "%";
        metricRatio.textContent = `${val.passed_required} Mandatory Criteria Passed`;

        if (score >= 80.0) {
            verdictPill.className = "verdict-pill verdict-pass";
            verdictText.textContent = "COMPLIANT / PASS";
            metricScore.style.color = "var(--success)";
        } else {
            verdictPill.className = "verdict-pill verdict-fail";
            verdictText.textContent = "NON-COMPLIANT / REJECT";
            metricScore.style.color = "var(--danger)";
        }

        // 2. Generic Font Size Metric (Rule 96(1)(i))
        if (metricFont) {
            if (fontData.status === "PASS") {
                metricFont.textContent = "PASS";
                metricFont.style.color = "var(--success)";
                metricFontSub.textContent = `Ratio: ${fontData.ratio || '1.3'}x (Rule 96(1)(i))`;
            } else {
                metricFont.textContent = "FAIL";
                metricFont.style.color = "var(--danger)";
                metricFontSub.textContent = "Brand larger than generic";
            }
        }

        // 3. Redline Metric
        if (rl.detected) {
            metricRedline.textContent = "PRESENT";
            metricRedline.style.color = "var(--accent)";
            const strip = rl.strips[0];
            metricRedlineSub.textContent = `${strip?.orientation || "Line"} (Ratio: ${strip?.aspect_ratio || "3.5+"})`;
        } else {
            metricRedline.textContent = "NONE";
            metricRedline.style.color = "var(--text-muted)";
            metricRedlineSub.textContent = "OTC / Non-Scheduled";
        }

        // 4. Barcode Metric
        if (bc.detected) {
            metricBarcode.textContent = "PASS";
            metricBarcode.style.color = "var(--success)";
            const payload = bc.details[0] ? bc.details[0].data : "Detected";
            metricBarcodeSub.textContent = `${bc.details[0]?.type || "1D/2D"} Verified`;
        } else {
            metricBarcode.textContent = "CONDITIONAL";
            metricBarcode.style.color = "var(--accent)";
            metricBarcodeSub.textContent = "Outer Carton Mandate";
        }

        // 5. Populate Checklist Cards (All 14 Pharmacopoeia Criteria)
        checklistContainer.innerHTML = "";
        const checks = val.field_checks;

        for (const [field, info] of Object.entries(checks)) {
            const isPass = info.status === "PASS";
            const isInfo = info.status.includes("INFO") || info.status.includes("CONDITIONAL");
            const badgeClass = isPass ? "pill-pass" : (isInfo ? "pill-info" : "pill-fail");

            const card = document.createElement("div");
            card.className = "check-item";

            card.innerHTML = `
                <div>
                    <div class="check-item-header">
                        <span class="check-title">${field}</span>
                        <span class="pill-badge ${badgeClass}">${info.status}</span>
                    </div>
                    <div class="check-desc">${info.description}</div>
                </div>
                <div class="check-match">${escapeHtml(info.extracted_value)}</div>
            `;
            checklistContainer.appendChild(card);
        }

        // 5. Annotated Image
        annotatedImage.src = data.annotated_image_url + "?t=" + new Date().getTime();
        btnDownloadImage.href = data.annotated_image_url;

        // If sample was used, update upload preview
        if (data.original_image_url) {
            imagePreview.src = data.original_image_url;
            dropzonePrompt.style.display = "none";
            previewWrapper.style.display = "block";
        }

        // 6. OCR Text View
        ocrTextBox.textContent = report.ocr_text_preview || "No text could be extracted.";

        // 7. JSON View
        jsonTextBox.textContent = JSON.stringify(report, null, 2);
        btnDownloadJson.href = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(report, null, 2));
    }

    // Copy OCR Text
    btnCopyOcr.addEventListener("click", () => {
        navigator.clipboard.writeText(ocrTextBox.textContent).then(() => {
            btnCopyOcr.textContent = "Copied!";
            setTimeout(() => {
                btnCopyOcr.textContent = "Copy Text";
            }, 2000);
        });
    });

    function escapeHtml(string) {
        if (!string) return "";
        return String(string)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
