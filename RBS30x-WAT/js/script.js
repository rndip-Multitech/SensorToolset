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
    const sensorType = document.getElementById("sensor-type");

    const waterPresent     = document.getElementById("water-present");
    const waterNotPresent  = document.getElementById("water-not-present");

    const thresholdSelect      = document.getElementById("threshold");
    const restoralMarginSelect = document.getElementById("restoral-margin");

    const waterHelpButton     = document.getElementById("water-help-button");
    const thresholdHelpButton = document.getElementById("threshold-help-button");
    const restoralHelpButton  = document.getElementById("restoral-help-button");

    const generateButton = document.getElementById("generate-button");
    const hexSection     = document.getElementById("hex-section");
    const hexOutput      = document.getElementById("hex-output");

    const copyButton = document.getElementById("copy-button");
    const howButton  = document.getElementById("how-button");


    /* ============================================================
       Populate numeric dropdowns (0–255)
    ============================================================ */
    function populate0to255(selectElement, defaultValue) {
        selectElement.innerHTML = "";
        for (let i = 0; i <= 255; i++) {
            const opt = document.createElement("option");
            opt.value = String(i);
            opt.textContent = String(i);
            if (i === defaultValue) {
                opt.selected = true;
            }
            selectElement.appendChild(opt);
        }
    }

    // Water threshold: default = 80
    populate0to255(thresholdSelect, 80);

    // Restoral margin: default = 0
    populate0to255(restoralMarginSelect, 0);


    /* ============================================================
       Help Button Popups
    ============================================================ */
    waterHelpButton.addEventListener("click", () => {
        showDialog(
            "Water Notification:\n\n" +
            "Enable Water Present Notification to receive alerts when water is detected.\n\n" +
            "Enable Water Not Present Notification to receive alerts when the sensor " +
            "returns to a dry condition."
        );
    });

    thresholdHelpButton.addEventListener("click", () => {
        showDialog(
            "Threshold Setting:\n\n" +
            "This sets the threshold of relative resistance between the water probes " +
            "on a scale of 0–255. Default is 80.\n\n" +
            "It is not recommended to change this setting. False alerts should be " +
            "addressed by improving probe placement, not changing the threshold."
        );
    });

    restoralHelpButton.addEventListener("click", () => {
        showDialog(
            "Restoral Margin Setting:\n\n" +
            "This defines how far the resistance must fall back below the threshold " +
            "before a restoration alert is triggered.\n\n" +
            "Range is 0–255. Default is 0."
        );
    });


    /* ============================================================
       Generate Hex Code
       Final format:
           08 + WP/NP hex + thresholdHex + restoralHex + 00000000
    ============================================================ */
    generateButton.addEventListener("click", () => {

        const wp = waterPresent.checked;
        const wnp = waterNotPresent.checked;

        let wpnpHex = "";

        if (wp && wnp) wpnpHex = "00";
        else if (wp && !wnp) wpnpHex = "02";
        else if (!wp && wnp) wpnpHex = "01";
        else wpnpHex = "03";

        const thresholdVal = Number(thresholdSelect.value);
        const restoralVal  = Number(restoralMarginSelect.value);

        const thresholdHex = thresholdVal.toString(16).padStart(2, "0");
        const restoralHex  = restoralVal.toString(16).padStart(2, "0");

        const finalHex = "08" + wpnpHex + thresholdHex + restoralHex + "00000000";

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
            const sensorType = "water";
            window.location.href = `../downlinks.html?hexcode=${encodeURIComponent(hexcode)}&sensorType=${encodeURIComponent(sensorType)}`;
        });
    }

});
