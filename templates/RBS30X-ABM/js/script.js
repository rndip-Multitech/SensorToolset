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
    const enableMovementStart = document.getElementById("enableMovementStart");
    const enableMovementStop = document.getElementById("enableMovementStop");
    const accelerationThreshold = document.getElementById("accelerationThreshold");
    const scalingFactor = document.getElementById("scalingFactor");
    const settlingWindow = document.getElementById("settlingWindow");

    const generateButton = document.getElementById("generate-button");
    const hexSection = document.getElementById("hex-section");
    const hexOutput = document.getElementById("hex-output");
    const copyButton = document.getElementById("copy-button");
    const howButton = document.getElementById("how-button");

    // Verify all required elements exist
    if (!generateButton) {
        console.error("Generate button not found!");
        return;
    }
    if (!hexSection) {
        console.error("Hex section not found!");
        return;
    }
    if (!hexOutput) {
        console.error("Hex output not found!");
        return;
    }


    /* ============================================================
       Help Button Popups
    ============================================================ */
    document.getElementById("about-movement").addEventListener("click", () => {
        showDialog(
            "Movement Notification:\n\n" +
            "Enable Reporting for Movement Start to receive alerts when the sensor detects motion.\n\n" +
            "Enable Reporting for Movement Stop to receive alerts when the sensor stops detecting motion."
        );
    });

    document.getElementById("about-threshold").addEventListener("click", () => {
        showDialog(
            "Acceleration Change Threshold:\n\n" +
            "This sets the threshold for detecting acceleration changes. The threshold value relates to the scaling factor selected.\n\n" +
            "The minimum setting is 5. Lower values are more sensitive to movement."
        );
    });

    document.getElementById("about-scaling").addEventListener("click", () => {
        showDialog(
            "Scaling Factor:\n\n" +
            "The scaling parameter defines the G-force range that the internal accelerometer operates with.\n\n" +
            "Lower settings (+/- 2g) are more sensitive than higher settings (+/- 16g).\n\n" +
            "Best practice: Use the largest scaling factor that the system allows and the smallest threshold."
        );
    });

    document.getElementById("about-settling").addEventListener("click", () => {
        showDialog(
            "Settling Window Time:\n\n" +
            "To prevent continuous reporting of movement events, a settling window ensures movement has stopped before the sensor reports a new event.\n\n" +
            "This defines the amount of time where the acceleration of all axes must stop changing before the sensor will report another event.\n\n" +
            "Default is 5 seconds. Range is 0.25 to 63 seconds."
        );
    });


    /* ============================================================
       Generate Hex Code
       Format: 0E + actHex + swtHex + scalingHex + startStopHex + 000000
    ============================================================ */
    generateButton.addEventListener("click", () => {
        console.log("Generate button clicked");

        const movStart = enableMovementStart ? enableMovementStart.checked : false;
        const movStop = enableMovementStop ? enableMovementStop.checked : false;

        if (!movStart && !movStop) {
            showDialog(
                "Please enable at least one of the following:\n" +
                "- Enable Reporting for Movement Start\n" +
                "- Enable Reporting for Movement Stop"
            );
            return;
        }

        // Start/Stop hex
        let startStopHex = "03";
        if (movStart && movStop) startStopHex = "00";
        else if (movStart && !movStop) startStopHex = "02";
        else if (!movStart && movStop) startStopHex = "01";

        const downlinkTypeHex = "0E";
        const actHex = accelerationThreshold ? accelerationThreshold.value : "05";
        const swtHex = settlingWindow ? settlingWindow.value : "14";
        const scalingHex = scalingFactor ? scalingFactor.value : "00";
        const pad = "000000";

        const finalHex = downlinkTypeHex + actHex + swtHex + scalingHex + startStopHex + pad;

        console.log("Generated hex:", finalHex);
        hexOutput.textContent = finalHex;
        hexSection.style.display = "block";
    });


    /* ============================================================
       Copy Hexcode
    ============================================================ */
    if (copyButton) {
        copyButton.addEventListener("click", () => {
            if (!hexOutput || !hexOutput.textContent) {
                showDialog("No hexcode to copy.");
                return;
            }
            navigator.clipboard.writeText(hexOutput.textContent)
                .then(() => showDialog("Hexcode copied."))
                .catch(() => showDialog("Unable to copy hexcode."));
        });
    }


    /* ============================================================
       How to Use Hexcode
    ============================================================ */
    if (howButton) {
        howButton.addEventListener("click", () => {
            showDialog(
                "1. Copy the generated hex string.\n" +
                "2. Paste it into your LoRaWAN server or gateway downlink tool. For MultiTech gateways, open the gateway's mPower web interface, choose LoRaWAN, Downlink Queue. Choose Add New, then paste the hexcode into the Data input box. Set Ack Attempts to 2 and Rx Window to 2.\n" +
                "3. Send the downlink to your RadioBridge sensor.\n" +
                "4. The sensor applies the configuration the next time it sends an uplink."
            );
        });
    }


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
            const sensorType = "accelerometer-based movement sensor";
            window.location.href = `../downlinks.html?hexcode=${encodeURIComponent(hexcode)}&sensorType=${encodeURIComponent(sensorType)}`;
        });
    }

});



