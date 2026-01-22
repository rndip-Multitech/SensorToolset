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
       Element References
    ============================================================ */
    const notificationType = document.getElementById("notificationType");
    const thresholdSection = document.getElementById("threshold-section");
    const rocSection = document.getElementById("roc-section");

    const upperTempThreshold = document.getElementById("upperTempThreshold");
    const lowerTempThreshold = document.getElementById("lowerTempThreshold");
    const restoralMarginTemp = document.getElementById("restoralMarginTemp");
    const upperHumidityThreshold = document.getElementById("upperHumidityThreshold");
    const lowerHumidityThreshold = document.getElementById("lowerHumidityThreshold");
    const restoralMarginHumidity = document.getElementById("restoralMarginHumidity");

    const tempIncrease = document.getElementById("tempIncrease");
    const tempDecrease = document.getElementById("tempDecrease");
    const humidityIncrease = document.getElementById("humidityIncrease");
    const humidityDecrease = document.getElementById("humidityDecrease");

    const periodicReporting = document.getElementById("periodicReporting");
    const timePeriod = document.getElementById("timePeriod");
    const timePeriodContainer = document.getElementById("timePeriodContainer");

    const generateButton = document.getElementById("generate-button");
    const hexSection = document.getElementById("hex-section");
    const hexOutput = document.getElementById("hex-output");
    const copyButton = document.getElementById("copy-button");
    const howButton = document.getElementById("how-button");


    /* ============================================================
       Populate Dropdowns
    ============================================================ */
    function populateDropdown(select, min, max, defaultValue) {
        select.innerHTML = "";
        for (let i = min; i <= max; i++) {
            const opt = document.createElement("option");
            opt.value = i;
            opt.textContent = i;
            if (i === defaultValue) opt.selected = true;
            select.appendChild(opt);
        }
    }

    // Temperature thresholds (-30 to 70)
    populateDropdown(lowerTempThreshold, -30, 70, 0);
    populateDropdown(upperTempThreshold, -30, 70, 40);

    // Restoral margins (0-15)
    populateDropdown(restoralMarginTemp, 0, 15, 0);
    populateDropdown(restoralMarginHumidity, 0, 15, 0);

    // Humidity thresholds (0-100)
    populateDropdown(lowerHumidityThreshold, 0, 100, 20);
    populateDropdown(upperHumidityThreshold, 0, 100, 80);

    // Report on Change (0-15)
    populateDropdown(tempIncrease, 0, 15, 5);
    populateDropdown(tempDecrease, 0, 15, 5);
    populateDropdown(humidityIncrease, 0, 15, 5);
    populateDropdown(humidityDecrease, 0, 15, 5);

    // Time period (1-127)
    populateDropdown(timePeriod, 1, 127, 1);


    /* ============================================================
       Mode Switching (Threshold vs Report on Change)
    ============================================================ */
    function updateModeSections() {
        const mode = notificationType.value;
        thresholdSection.style.display = (mode === "threshold") ? "block" : "none";
        rocSection.style.display = (mode === "reportOnChange") ? "block" : "none";
    }
    notificationType.addEventListener("change", updateModeSections);
    updateModeSections();


    /* ============================================================
       Periodic Reporting Visibility
    ============================================================ */
    function updatePeriodicVisibility() {
        const mode = periodicReporting.value;
        timePeriodContainer.style.display = (mode === "disabled") ? "none" : "flex";
    }
    periodicReporting.addEventListener("change", updatePeriodicVisibility);
    updatePeriodicVisibility();


    /* ============================================================
       Help Button Popups
    ============================================================ */
    document.getElementById("about-mode").addEventListener("click", () => {
        showDialog(
            "Notification Type:\n\n" +
            "Threshold Mode: Set upper and lower temperature and humidity thresholds. The sensor sends alerts when values cross these thresholds.\n\n" +
            "Report on Change Mode: The sensor sends alerts when temperature or humidity changes by a specified amount from the last report."
        );
    });

    document.getElementById("about-restoral-temp").addEventListener("click", () => {
        showDialog(
            "Restoral Margin - Temperature:\n\n" +
            "The Restoral Margin requires the temperature to cross back over the threshold by this amount before a new event is reported.\n\n" +
            "This prevents excessive messages when temperature is near the threshold. Range is 0-15°C. Set to 0 to disable."
        );
    });

    document.getElementById("about-restoral-hum").addEventListener("click", () => {
        showDialog(
            "Restoral Margin - Humidity:\n\n" +
            "The Restoral Margin requires the humidity to cross back over the threshold by this amount before a new event is reported.\n\n" +
            "This prevents excessive messages when humidity is near the threshold. Range is 0-15%. Set to 0 to disable."
        );
    });

    document.getElementById("about-temp-roc").addEventListener("click", () => {
        showDialog(
            "Temperature Change Settings:\n\n" +
            "Temperature Increase: Alert when temperature rises by this amount from the last report.\n\n" +
            "Temperature Decrease: Alert when temperature falls by this amount from the last report.\n\n" +
            "Range is 0-15°C."
        );
    });

    document.getElementById("about-hum-roc").addEventListener("click", () => {
        showDialog(
            "Humidity Change Settings:\n\n" +
            "Humidity Increase: Alert when humidity rises by this amount from the last report.\n\n" +
            "Humidity Decrease: Alert when humidity falls by this amount from the last report.\n\n" +
            "Range is 0-15%."
        );
    });

    document.getElementById("about-periodic").addEventListener("click", () => {
        showDialog(
            "Periodic Reporting:\n\n" +
            "Disabled – no periodic transmissions.\n" +
            "Minutes – transmit every N minutes.\n" +
            "Hours – transmit every N hours.\n\n" +
            "The sensor can send periodic updates in either Threshold or Report on Change mode."
        );
    });


    /* ============================================================
       Hex Helpers
    ============================================================ */
    function toHex(value, size) {
        let v = parseInt(value);
        if (v < 0) v = 256 + v;
        let hex = v.toString(16).toUpperCase();
        while (hex.length < size) hex = "0" + hex;
        return hex.slice(-size);
    }


    /* ============================================================
       Generate Hex Code
       Format: 0D + roc_or_thresh + periodic + hum_restoral + temp_restoral + 
               temp_low/roc_up + temp_hi/roc_down + hum_low/roc_up + hum_hi/roc_down
    ============================================================ */
    generateButton.addEventListener("click", () => {

        const downlinkTypeHex = "0D";
        const mode = notificationType.value;
        const rocOrThreshHex = (mode === "threshold") ? "00" : "01";

        // Periodic reporting hex
        let periodicHex = "00";
        if (periodicReporting.value === "minutes") {
            periodicHex = toHex(parseInt(timePeriod.value) + 128, 2);
        } else if (periodicReporting.value === "hours") {
            periodicHex = toHex(parseInt(timePeriod.value), 2);
        }

        // Restoral margins (single hex digit each, combined)
        const tempRestoralHex = parseInt(restoralMarginTemp.value).toString(16).toUpperCase();
        const humRestoralHex = parseInt(restoralMarginHumidity.value).toString(16).toUpperCase();

        let tempLowRocUpHex, tempHiRocDownHex, humLowRocUpHex, humHiRocDownHex;

        if (mode === "threshold") {
            tempLowRocUpHex = toHex(parseInt(lowerTempThreshold.value), 2);
            tempHiRocDownHex = toHex(parseInt(upperTempThreshold.value), 2);
            humLowRocUpHex = toHex(parseInt(lowerHumidityThreshold.value), 2);
            humHiRocDownHex = toHex(parseInt(upperHumidityThreshold.value), 2);
        } else {
            tempLowRocUpHex = "0" + toHex(parseInt(tempIncrease.value), 1);
            tempHiRocDownHex = "0" + toHex(parseInt(tempDecrease.value), 1);
            humLowRocUpHex = "0" + toHex(parseInt(humidityIncrease.value), 1);
            humHiRocDownHex = "0" + toHex(parseInt(humidityDecrease.value), 1);
        }

        const finalHex = downlinkTypeHex + rocOrThreshHex + periodicHex + 
                         humRestoralHex + tempRestoralHex + 
                         tempLowRocUpHex + tempHiRocDownHex + 
                         humLowRocUpHex + humHiRocDownHex;

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
            const sensorType = "temperature and humidity";
            window.location.href = `../downlinks.html?hexcode=${encodeURIComponent(hexcode)}&sensorType=${encodeURIComponent(sensorType)}`;
        });
    }

});



