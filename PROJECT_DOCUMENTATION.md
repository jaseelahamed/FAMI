

    ```
    https://your-service-name.onrender.com/health
    ```
  - It should respond with:
    ```json
    {
      "status": "ok",
      "service": "Pharma Label Scanner",
      "version": "1.0.0",
      "tesseract_detected": true
    }
    ```
    If `"tesseract_detected": false`, your Render service was deployed as a Python service rather than a Docker service. Redeploy selecting **Docker**.

---

*Authored for Pharmaceutical Regulatory Inspection & Academic Research.*
