document.addEventListener("DOMContentLoaded", () => {
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
    const errorBanner = document.getElementById("errorBanner");
    const errorTitle = document.getElementById("errorTitle");
    const errorMessage = document.getElementById("errorMessage");
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

    const themeToggle = document.getElementById("themeToggle");
    const themeToggleText = document.getElementById("themeToggleText");

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        const toDark = theme !== "dark";
        themeToggleText.textContent = toDark ? "Dark mode" : "Light mode";
        themeToggle.setAttribute("aria-label", toDark ? "Switch to dark mode" : "Switch to light mode");
    }

    applyTheme(document.documentElement.getAttribute("data-theme") || "light");

    themeToggle.addEventListener("click", () => {
        const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        applyTheme(next);
        try { localStorage.setItem("theme", next); } catch (e) {}
    });

    let selectedFile = null;
    let progressTimer = null;
    let scanToken = 0; // invalidates in-flight scans when the image is removed

    // Check engine status
    fetch("/health")
        .then(res => res.json())
        .then(data => {
            const badge = document.getElementById("systemStatusBadge");
            if (badge && data.ai_engine) {
                badge.innerHTML = `${data.ai_engine} &bull; Active`;
            }
        })
        .catch(() => {});

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

    dropzonePrompt.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileInput.click();
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

        clearResults();
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

    function clearResults() {
        scanToken++; // ignore any scan response still in flight
        clearInterval(progressTimer);
        scanProgress.style.display = "none";
        hideError();
        resultsContent.style.display = "none";
        emptyState.style.display = "block";
        verdictPill.style.display = "none";
        verdictPill.className = "verdict-pill";
        verdictText.textContent = "Awaiting Scan";
        checklistContainer.innerHTML = "";
        annotatedImage.removeAttribute("src");
        btnDownloadImage.href = "#";
        ocrTextBox.textContent = "";
        jsonTextBox.textContent = "";
        btnDownloadJson.href = "#";
        metricScore.textContent = "0%";
        metricScore.style.color = "";
        metricRatio.textContent = "0/14 Passed";
        [metricFont, metricRedline, metricBarcode].forEach((el) => {
            el.textContent = "--";
            el.style.color = "";
        });
        metricFontSub.textContent = "Rule 96(1)(i) Ratio";
        metricRedlineSub.textContent = "HSV Contour Analysis";
        metricBarcodeSub.textContent = "GS1 Standards";
        // Return to the first tab
        tabButtons.forEach((b) => b.classList.remove("active"));
        tabPanes.forEach((p) => p.classList.remove("active"));
        tabButtons[0].classList.add("active");
        tabPanes[0].classList.add("active");
        btnSample.disabled = false;
    }

    function clearFileSelection() {
        clearResults();
        selectedFile = null;
        fileInput.value = "";
        imagePreview.src = "";
        previewWrapper.style.display = "none";
        dropzonePrompt.style.display = "flex";
        btnScan.disabled = true;
    };

    tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            tabButtons.forEach((b) => b.classList.remove("active"));
            tabPanes.forEach((p) => p.classList.remove("active"));

            btn.classList.add("active");
            const targetPane = document.getElementById("tab-" + targetTab);
            if (targetPane) targetPane.classList.add("active");
        });
    });

    btnScan.addEventListener("click", () => {
        if (!selectedFile) return;
        const formData = new FormData();
        formData.append("image", selectedFile);
        formData.append("is_sample", "false");
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
            { threshold: 40, text: "Multi-orientation OCR text scanning..." },
            { threshold: 65, text: "HSV Dual-Band Schedule Redline Detection..." },
            { threshold: 80, text: "Measuring Font Size Bounding Boxes (Rule 96(1)(i))..." },
            { threshold: 92, text: "Verifying 14 Pharmacopoeia Statutory Regulatory Criteria..." },
            { threshold: 18, text: "Auto-Cropping Letterbox Margins & Enhancing Image..." },
            { threshold: 38, text: "Connecting to Google Gemini Multimodal Vision AI..." },
            { threshold: 60, text: "Semantically Auditing 14 Pharmacopoeia Statutory Criteria..." },
            { threshold: 78, text: "Verifying Rule 96(1)(i) Brand vs Generic Font Hierarchy..." },
            { threshold: 90, text: "Generating Inspection Scorecard & Annotated Overlay..." }
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

    function showError(title, msg) {
        if (errorBanner && errorMessage) {
            if (errorTitle) errorTitle.textContent = title;
            errorMessage.textContent = msg;
            errorBanner.style.display = "block";
        }
        emptyState.style.display = "block";
        resultsContent.style.display = "none";
        verdictPill.style.display = "none";
    }

    function hideError() {
        if (errorBanner) errorBanner.style.display = "none";
    }

    async function performScan(formData) {
        const myToken = ++scanToken;
        btnScan.disabled = true;
        btnSample.disabled = true;
        hideError();
        startProgressAnimation();

        try {
            const response = await fetch("/api/scan", {
                method: "POST",
                body: formData
            });

            let data;
            const textResponse = await response.text();
            if (myToken !== scanToken) return; // image was removed while scanning
            try {
                data = JSON.parse(textResponse);
            } catch (jsonErr) {
                if (response.status === 502 || response.status === 504) {
                    showError(
                        "Cloud Server Timeout (HTTP " + response.status + ")",
                        "The server timed out processing the image. Please try again."
                    );
                } else {
                    showError(
                        "Server Response Error (HTTP " + response.status + ")",
                        textResponse.substring(0, 300) || "Invalid server response."
                    );
                }
                return;
            }

            if (!response.ok || !data.success) {
                const errText = data.error || ("Inspection failed with HTTP " + response.status);
                showError("Inspection Error", errText);
                return;
            }

            renderResults(data);

        } catch (error) {
            if (myToken !== scanToken) return;
            console.error("Scan request failed:", error);
            showError("Network Connection Error", "Could not connect to the inspection server.");
        } finally {
            if (myToken === scanToken) {
                stopProgressAnimation();
                btnScan.disabled = !selectedFile;
                btnSample.disabled = false;
            }
        }
    }

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

        if (val.overall_status === "COMPLIANT / PASS") {
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
                metricFontSub.textContent = `Measured ratio: ${fontData.ratio}x`;
            } else {
                metricFont.textContent = "FAIL";
                metricFont.style.color = "var(--danger)";
                metricFontSub.textContent = fontData.details || "Font measurement unavailable";
            }
        }

        // 3. Redline Metric
        if (rl.detected) {
            metricRedline.textContent = "PRESENT";
            metricRedline.style.color = "var(--accent)";
            const strip = rl.strips[0];
            metricRedlineSub.textContent = `${strip?.orientation || "Line"} (Schedule H)`;
        } else {
            metricRedline.textContent = "NONE";
            metricRedline.style.color = "var(--text-muted)";
            metricRedlineSub.textContent = "OTC / Non-Scheduled";
        }

        // 4. Barcode Metric
        if (bc.detected) {
            metricBarcode.textContent = "PASS";
            metricBarcode.style.color = "var(--success)";
            metricBarcodeSub.textContent = "Barcode / QR code present";
        } else {
            metricBarcode.textContent = "OPTIONAL";
            metricBarcode.style.color = "var(--accent)";
            metricBarcodeSub.textContent = "Not detected — optional";
        }

        // 5. Populate Checklist Cards (All 14 Pharmacopoeia Criteria)
        checklistContainer.innerHTML = "";
        const checks = val.field_checks;

        for (const [field, info] of Object.entries(checks)) {
            const isPass = info.status === "PASS";
            const badgeClass = isPass ? "pill-pass" : (info.required === false ? "pill-info" : "pill-fail");

            const card = document.createElement("div");
            card.className = "check-item";

            card.innerHTML = `
                <div>
                    <div class="check-item-header">
                        <span class="check-title">${field}${info.required === false ? " (Optional)" : ""}</span>
                        <span class="pill-badge ${badgeClass}">${info.status}</span>
                    </div>
                    <div class="check-desc">${info.description}</div>
                </div>
                <div class="check-match">${escapeHtml(info.extracted_value)}</div>
                ${info.review_notes?.length ? `<div class="check-desc">${info.review_notes.map(escapeHtml).join("<br>")}</div>` : ""}
            `;
            checklistContainer.appendChild(card);
        }

        // 6. Annotated Image
        annotatedImage.src = data.annotated_image_url + "?t=" + new Date().getTime();
        btnDownloadImage.href = data.annotated_image_url;

        // If sample was used, update upload preview
        if (data.original_image_url) {
            imagePreview.src = data.original_image_url;
            dropzonePrompt.style.display = "none";
            previewWrapper.style.display = "block";
        }

        // 6. OCR Text View
        ocrTextBox.textContent = report.ocr_text_full || report.ocr_text_preview || "No text could be extracted.";
        // 7. OCR Text View
        ocrTextBox.textContent = report.ocr_text_preview || "No text could be extracted.";

        // 8. JSON View
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
