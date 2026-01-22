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
       Helper: Convert decimal to 2-character hex
    ============================================================ */
    function toHex2(value) {
        return parseInt(value).toString(16).padStart(2, '0').toUpperCase();
    }

    /* ============================================================
       Helper: Convert decimal to 4-character hex
    ============================================================ */
    function toHex4(value) {
        return parseInt(value).toString(16).padStart(4, '0').toUpperCase();
    }

    /* ============================================================
       Element References
    ============================================================ */
    const reportingType = document.getElementById("reportingType");
    const thresholdSection = document.getElementById("thresholdSection");
    const rocSection = document.getElementById("rocSection");
    const lowerDistanceThreshold = document.getElementById("lowerDistanceThreshold");
    const upperDistanceThreshold = document.getElementById("upperDistanceThreshold");
    const distanceIncrease = document.getElementById("distanceIncrease");
    const distanceDecrease = document.getElementById("distanceDecrease");
    const holdTimeScale = document.getElementById("holdTimeScale");
    const holdTimePeriod = document.getElementById("holdTimePeriod");
    const periodicReporting = document.getElementById("periodicReporting");
    const timePeriod = document.getElementById("timePeriod");
    const timePeriodLabel = document.getElementById("timePeriodLabel");

    const aboutReportingBtn = document.getElementById("about-reporting-button");

    const generateButton = document.getElementById("generate-button");
    const hexSection = document.getElementById("hex-section");
    const hexOutput = document.getElementById("hex-output");

    const copyButton = document.getElementById("copy-button");
    const howButton = document.getElementById("how-button");


    /* ============================================================
       Show/Hide Sections Based on Reporting Type
    ============================================================ */
    reportingType.addEventListener("change", () => {
        if (reportingType.value === "threshold") {
            thresholdSection.style.display = "block";
            rocSection.style.display = "none";
        } else {
            thresholdSection.style.display = "none";
            rocSection.style.display = "block";
        }
    });


    /* ============================================================
       Populate Time Period Dropdown Based on Time Scale
    ============================================================ */
    function populateTimePeriod() {
        timePeriod.innerHTML = "";
        const scale = periodicReporting.value;

        if (scale === "disabled") {
            timePeriod.style.display = "none";
            timePeriodLabel.style.display = "none";
        } else {
            timePeriod.style.display = "inline-block";
            timePeriodLabel.style.display = "inline-block";

            for (let i = 1; i <= 127; i++) {
                const option = document.createElement("option");
                option.value = i;
                option.textContent = i;
                timePeriod.appendChild(option);
            }
        }
    }

    periodicReporting.addEventListener("change", populateTimePeriod);
    populateTimePeriod(); // Initialize on page load


    /* ============================================================
       About Periodic Reporting Settings
    ============================================================ */
    aboutReportingBtn.addEventListener("click", () => {
        showDialog(
            "Set how often the sensor reports its current level reading.\n\n" +
            "Time Scale: Choose Minutes or Hours, or Disabled to turn off periodic reporting.\n\n" +
            "Time Period: Select the number of minutes or hours between reports.\n\n" +
            "Shorter intervals provide more frequent updates but consume more battery."
        );
    });


    /* ============================================================
       Generate Hex Code
    ============================================================ */
    generateButton.addEventListener("click", () => {
        // Characters 1-2: Downlink type for ultrasonic level sensor
        const downlinkTypeHex = "10";

        // Characters 3-4: Reporting type hex
        const reportingTypeHex = reportingType.value === "threshold" ? "00" : "01";

        // Characters 5-6: Periodic reporting hex value
        let periodicHex = "00";
        if (periodicReporting.value === "minutes") {
            periodicHex = toHex2(parseInt(timePeriod.value) + 128);
        } else if (periodicReporting.value === "hours") {
            periodicHex = toHex2(timePeriod.value);
        }

        // Characters 7-8: Hold time hex value
        // Seconds: value + 128, Minutes: just value
        let holdTimeHex = "00";
        if (holdTimeScale.value === "seconds") {
            holdTimeHex = toHex2(parseInt(holdTimePeriod.value) + 128);
        } else if (holdTimeScale.value === "minutes") {
            holdTimeHex = toHex2(holdTimePeriod.value);
        }

        // Threshold or ROC values
        let value1Hex, value2Hex, pad;

        if (reportingType.value === "threshold") {
            // Characters 9-12: Lower Distance Threshold as 4-character hex
            // Characters 13-16: Upper Distance Threshold as 4-character hex
            value1Hex = toHex4(lowerDistanceThreshold.value);
            value2Hex = toHex4(upperDistanceThreshold.value);
            pad = "00"; // 2 characters padding
        } else {
            // Characters 9-10: Distance Increase as 2-character hex
            // Characters 11-12: Distance Decrease as 2-character hex
            value1Hex = toHex2(distanceIncrease.value);
            value2Hex = toHex2(distanceDecrease.value);
            pad = "000000"; // 6 characters padding
        }

        // Build the full hexcode
        const fullHex = downlinkTypeHex + reportingTypeHex + periodicHex + holdTimeHex + value1Hex + value2Hex + pad;

        hexOutput.textContent = fullHex;
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


    /* ============================================================
       Schedule Downlink
    ============================================================ */
    const scheduleButton = document.getElementById("schedule-button");
    if (scheduleButton) {
        scheduleButton.addEventListener("click", () => {
            const hexcode = hexOutput.textContent;
            if (!hexcode) {
                showDialog("Please generate a hexcode first.");
                return;
            }
            // Redirect to downlinks page with hexcode and sensor type
            const sensorType = "ultrasonic distance sensor";
            window.location.href = `../downlinks.html?hexcode=${encodeURIComponent(hexcode)}&sensorType=${encodeURIComponent(sensorType)}`;
        });
    }

});

