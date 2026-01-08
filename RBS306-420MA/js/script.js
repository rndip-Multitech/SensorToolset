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
    const lowerThreshold = document.getElementById("lowerThreshold");
    const upperThreshold = document.getElementById("upperThreshold");
    const reportingInterval = document.getElementById("reportingInterval");

    const aboutThresholdBtn = document.getElementById("about-threshold-button");
    const aboutIntervalBtn = document.getElementById("about-interval-button");

    const generateButton = document.getElementById("generate-button");
    const hexSection = document.getElementById("hex-section");
    const hexOutput = document.getElementById("hex-output");

    const copyButton = document.getElementById("copy-button");
    const howButton = document.getElementById("how-button");


    /* ============================================================
       About Threshold Settings
    ============================================================ */
    aboutThresholdBtn.addEventListener("click", () => {
        showDialog(
            "Set the lower and upper thresholds for the 4-20 mA current measurement.\n\n" +
            "When the measured current falls below the lower threshold or rises above " +
            "the upper threshold, an alert notification will be sent.\n\n" +
            "Valid range: 4 mA to 20 mA"
        );
    });


    /* ============================================================
       About Reporting Interval
    ============================================================ */
    aboutIntervalBtn.addEventListener("click", () => {
        showDialog(
            "The reporting interval determines how often the sensor sends " +
            "periodic status updates, regardless of threshold alerts.\n\n" +
            "Choose a shorter interval for more frequent updates, or a longer " +
            "interval to conserve battery life."
        );
    });


    /* ============================================================
       Generate Hex Code
    ============================================================ */
    generateButton.addEventListener("click", () => {
        const lower = parseFloat(lowerThreshold.value);
        const upper = parseFloat(upperThreshold.value);

        // Validate thresholds
        if (lower < 4 || lower > 20) {
            showDialog("Lower threshold must be between 4 and 20 mA.");
            return;
        }
        if (upper < 4 || upper > 20) {
            showDialog("Upper threshold must be between 4 and 20 mA.");
            return;
        }
        if (lower >= upper) {
            showDialog("Lower threshold must be less than upper threshold.");
            return;
        }

        // Convert thresholds to hex (multiply by 10 to preserve one decimal place)
        const lowerHex = Math.round(lower * 10).toString(16).toUpperCase().padStart(4, '0');
        const upperHex = Math.round(upper * 10).toString(16).toUpperCase().padStart(4, '0');

        const intervalHex = reportingInterval.value;

        const downlinkTypeHex = "0A"; // Downlink type for 4-20 mA sensor
        const pad = "0000";

        const fullHex =
            downlinkTypeHex +
            lowerHex +
            upperHex +
            intervalHex +
            pad;

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

});


