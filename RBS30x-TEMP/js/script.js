document.addEventListener("DOMContentLoaded", () => {

    /* ============================================================
       Modal Dialog
    ============================================================ */
    function showDialog(message) {
        const existing = document.querySelector(".modal-overlay");
        if (existing) existing.remove();

        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";

        const box = document.createElement("div");
        box.className = "modal-box";

        const msg = document.createElement("div");
        msg.style.whiteSpace = "pre-line";
        msg.textContent = message;
        box.appendChild(msg);

        const btn = document.createElement("button");
        btn.textContent = "OK";
        btn.style.marginTop = "14px";
        btn.addEventListener("click", () => overlay.remove());
        box.appendChild(btn);

        overlay.appendChild(box);
        document.body.appendChild(overlay);
    }


    /* ============================================================
       Element references
    ============================================================ */
    const periodicReporting = document.getElementById("periodic-reporting");
    const timePeriod = document.getElementById("time-period");
    const timePeriodLabel = document.getElementById("time-period-label");

    const modeSelect = document.getElementById("mode-select");
    const sensorType = document.getElementById("sensor-type");

    const rocSection = document.getElementById("roc-section");
    const thresholdSection = document.getElementById("threshold-section");

    const generateButton = document.getElementById("generate-button");
    const hexSection = document.getElementById("hex-section");
    const hexOutput = document.getElementById("hex-output");
    const copyButton = document.getElementById("copy-button");
    const howButton = document.getElementById("how-button");

    const aboutPeriodicBtn = document.getElementById("about-periodic-button");
    const aboutModeBtn = document.getElementById("about-mode-button");


    /* ============================================================
       Populate Time Period 1–127
    ============================================================ */
    function populateTimePeriod() {
        timePeriod.innerHTML = "";
        for (let i = 1; i <= 127; i++) {
            const opt = document.createElement("option");
            opt.value = i;
            opt.textContent = i;
            timePeriod.appendChild(opt);
        }
    }
    populateTimePeriod();


    /* ============================================================
       Periodic Reporting Visibility
    ============================================================ */
    function updateTimeVisibility() {
        const mode = periodicReporting.value;
        const show = (mode === "minutes" || mode === "hours");

        timePeriod.style.display = show ? "inline-block" : "none";
        timePeriodLabel.style.display = show ? "inline-block" : "none";
    }
    periodicReporting.addEventListener("change", updateTimeVisibility);
    updateTimeVisibility();


    /* ============================================================
       Help: Periodic Reporting
    ============================================================ */
    aboutPeriodicBtn.addEventListener("click", () => {
        showDialog(
            "Periodic Reporting:\n\n" +
            "Disabled – no periodic transmissions.\n" +
            "Minutes – transmit every N minutes.\n" +
            "Hours – transmit every N hours."
        );
    });


    /* ============================================================
       Help: Reporting Mode
    ============================================================ */
    aboutModeBtn.addEventListener("click", () => {
        showDialog(
            "Threshold Mode: The upper and lower temperature thresholds are signed values with units of one degree Celsius.\n" +
            "Note that if the configuration settings exceed the maximum ratings on the sensor, the sensor may not report an event.\n\n" +

            "Report on Change Mode:\n" +
            "If the temperature increase or decrease are non-zero, then the sensor sends an alert any time the temperature changes " +
            "by the specified amount. For example, if the temperature increase and decrease are set to 5 degrees, then an alert is sent " +
            "every time the temperature changes 5 degrees from the last report. The temperature increase and decrease are unsigned values " +
            "with units in degrees C."
        );
    });


    /* ============================================================
       ROC/Threshold Mode Switching
    ============================================================ */
    function updateModeSections() {
        const mode = modeSelect.value;

        rocSection.style.display = (mode === "roc") ? "block" : "none";
        thresholdSection.style.display = (mode === "threshold") ? "block" : "none";
    }
    modeSelect.addEventListener("change", updateModeSections);
    updateModeSections();


    /* ============================================================
       Hex Helpers
    ============================================================ */
    function hexByte(v) {
        v = Number(v);
        if (!Number.isFinite(v)) v = 0;
        v = Math.max(0, Math.min(255, v));
        return v.toString(16).padStart(2, "0");
    }

    function signedHexByte(v) {
        v = Number(v);
        if (!Number.isFinite(v)) v = 0;
        v = Math.max(-128, Math.min(127, v));
        if (v < 0) v = 256 + v;
        return v.toString(16).padStart(2, "0");
    }

    function periodicHex(mode, value) {
        const p = Number(value);
        if (!Number.isFinite(p) || p < 1 || p > 127) return "00";

        if (mode === "disabled") return "00";
        if (mode === "minutes") return (0x80 + p).toString(16).padStart(2, "0");
        if (mode === "hours") return p.toString(16).padStart(2, "0");

        return "00";
    }


    /* ============================================================
       Generate Hexcode
    ============================================================ */
    generateButton.addEventListener("click", () => {

        const selectedMode = modeSelect.value;
        if (!selectedMode) {
            showDialog("Please select a reporting mode.");
            return;
        }

        const extSensors = [
            "RBS-306-TEMP-EXT",
            "RBS301-TEMP-EXT",
            "RBS3010NA05BN00"
        ];

        const dnType = extSensors.includes(sensorType.value) ? "09" : "19";
        const pHex = periodicHex(periodicReporting.value, timePeriod.value);

        /* Restoral Margin */
        let restoralMargin = "00";
        if (selectedMode === "threshold") {
            const rm = Number(document.getElementById("restoral-margin").value);
            if (rm >= 0 && rm <= 15) {
                restoralMargin = rm.toString(16).padStart(2, "0");
            }
        }

        /* Byte5 / Byte6 logic */
        let byte5 = "00";
        let byte6 = "00";

        if (selectedMode === "threshold") {
            byte5 = signedHexByte(document.getElementById("threshold-lower").value);
            byte6 = signedHexByte(document.getElementById("threshold-upper").value);
        }

        if (selectedMode === "roc") {
            byte5 = hexByte(document.getElementById("roc-sensitivity").value);
            byte6 = hexByte(document.getElementById("roc-interval").value);
        }

        const notif = (selectedMode === "threshold") ? "00" : "01";
        const pad = "0000";

        const finalHex =
            dnType +
            notif +
            pHex +
            restoralMargin +
            byte5 +
            byte6 +
            pad;

        hexOutput.textContent = finalHex;
        hexSection.style.display = "block";
    });


    /* ============================================================
       Copy Hexcode
    ============================================================ */
    copyButton.addEventListener("click", () => {
        if (!hexOutput.textContent) {
            showDialog("No hexcode to copy.");
            return;
        }
        navigator.clipboard.writeText(hexOutput.textContent)
            .then(() => showDialog("Hexcode copied."))
            .catch(() => showDialog("Unable to copy hexcode."));
    });


    /* ============================================================
       How to Use Hexcode
    ============================================================ */
    howButton.addEventListener("click", () => {
        showDialog(
            "1. Copy the generated hex string.\n" +
            "2. Paste it into your LoRaWAN server or gateway downlink tool. For MultiTech gateways, open the gateway's mPower web interface, choose LoRaWAN, Downlink Queue. Choose Add New, then paste the hexcode into the Data input box. Set Ack Attempts to 2 and Rx Window to 2.\n" +
            "3. Send the downlink to your RadioBridge sensor.\n" +
            "4. The sensor applies the configuration the next time it sends an uplink."
        );
    });

});
