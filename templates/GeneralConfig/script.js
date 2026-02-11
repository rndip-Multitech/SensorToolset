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
    const disableAllEvents = document.getElementById("disableAllEvents");
    const useConfirmedMessages = document.getElementById("useConfirmedMessages");
    const enableADR = document.getElementById("enableADR");
    const numRetries = document.getElementById("numRetries");
    const enableSupervisoryMessages = document.getElementById("enableSupervisoryMessages");
    const timeInterval = document.getElementById("timeInterval");
    const samplingPeriod = document.getElementById("samplingPeriod");
    const timePeriod = document.getElementById("timePeriod");
    const timePeriodRow = document.getElementById("timePeriodRow");

    const generateButton = document.getElementById("generate-button");
    const hexSection = document.getElementById("hex-section");
    const hexOutput = document.getElementById("hex-output");
    const copyButton = document.getElementById("copy-button");
    const howButton = document.getElementById("how-button");


    /* ============================================================
       Populate Time Interval (1–127)
    ============================================================ */
    function populateTimeInterval() {
        timeInterval.innerHTML = "";
        for (let i = 1; i <= 127; i++) {
            const opt = document.createElement("option");
            opt.value = i;
            opt.textContent = i;
            timeInterval.appendChild(opt);
        }
    }
    populateTimeInterval();


    /* ============================================================
       Sampling Period Visibility
    ============================================================ */
    function updateTimePeriodOptions() {
        const sp = samplingPeriod.value;

        if (sp === "unchanged") {
            timePeriodRow.style.display = "none";
            timePeriod.innerHTML = "";
            return;
        }

        timePeriodRow.style.display = "flex";
        timePeriod.innerHTML = "";

        if (sp === "milliseconds") {
            for (let i = 250; i <= 15000; i += 250) {
                const opt = document.createElement("option");
                opt.value = i;
                opt.textContent = i;
                timePeriod.appendChild(opt);
            }
        } else {
            for (let i = 1; i <= 63; i++) {
                const opt = document.createElement("option");
                opt.value = i;
                opt.textContent = i;
                timePeriod.appendChild(opt);
            }
        }
    }
    samplingPeriod.addEventListener("change", updateTimePeriodOptions);
    updateTimePeriodOptions();


    /* ============================================================
       Disable All Events Warning
    ============================================================ */
    disableAllEvents.addEventListener("change", () => {
        if (disableAllEvents.checked) {
            showDialog("Disabling all events will cause the sensor to stop sending notification events and updates.");
        }
    });


    /* ============================================================
       Help Button Popups
    ============================================================ */
    document.getElementById("about-disable-events").addEventListener("click", () => {
        showDialog("Disabling all events will cause the sensor to stop sending notification events and updates.");
    });

    document.getElementById("about-confirmed").addEventListener("click", () => {
        showDialog("Use Confirmed Messages will ensure that messages are acknowledged by the network. When selected, you must choose the number of retries that the sensor will issue.");
    });

    document.getElementById("about-adr").addEventListener("click", () => {
        showDialog("Enabling Adaptive Data Rate allows the sensor to dynamically adjust the transmission data rate.");
    });

    document.getElementById("about-retries").addEventListener("click", () => {
        showDialog("Choose the number of retries the sensor should attempt before giving up.");
    });

    document.getElementById("about-supervisory").addEventListener("click", () => {
        showDialog("Enable Supervisory Messages to periodically send sensor status updates.");
    });

    document.getElementById("about-sampling").addEventListener("click", () => {
        showDialog("Contact MultiTech for guidance before modifying this setting.");
    });


    /* ============================================================
       Hex Calculation Helpers
    ============================================================ */
    function calculateRadioHex() {
        const adr = enableADR.checked;
        const confirm = useConfirmedMessages.checked;
        const retries = numRetries.value;

        if (adr && confirm) {
            return calculateRadioHexWithRetries(retries,
                "00", "04", "08", "0C", "10", "14", "18", "1C"
            );
        }
        if (!adr && confirm) {
            return calculateRadioHexWithRetries(retries,
                "01", "05", "09", "0D", "11", "15", "19", "1D"
            );
        }
        if (adr && !confirm) return "06";
        return "07";
    }

    function calculateRadioHexWithRetries(retries, hex0, hex1, hex2, hex3, hex4, hex5, hex6, hex7) {
        switch (retries) {
            case "1": return hex1;
            case "2": return hex2;
            case "3": return hex3;
            case "4": return hex4;
            case "5": return hex5;
            case "6": return hex6;
            case "7": return hex7;
            default: return hex0;
        }
    }

    function calculateSupervisoryHex() {
        const timeType = document.querySelector('input[name="timeType"]:checked').value;
        const interval = parseInt(timeInterval.value);

        if (timeType === "minutes") {
            return (0x80 + interval).toString(16).toUpperCase().padStart(2, "0");
        }
        return interval.toString(16).padStart(2, "0").toUpperCase();
    }

    function calculateSamplingPeriodHex() {
        const sp = samplingPeriod.value;
        const tp = parseInt(timePeriod.value) || 0;

        if (sp === "seconds") return (tp + 64).toString(16).toUpperCase().padStart(2, "0");
        if (sp === "minutes") return (tp + 128).toString(16).toUpperCase().padStart(2, "0");
        if (sp === "hours") return (tp + 192).toString(16).toUpperCase().padStart(2, "0");
        if (sp === "milliseconds") return Math.floor(tp / 250).toString(16).toUpperCase().padStart(2, "0");

        return "";
    }


    /* ============================================================
       Generate Hexcode
    ============================================================ */
    generateButton.addEventListener("click", () => {
        const downlinkTypeHex = "01";
        const daeHex = disableAllEvents.checked ? "01" : "00";
        const radioHex = calculateRadioHex();
        const superPerHex = calculateSupervisoryHex();
        const spHex = calculateSamplingPeriodHex();
        const pad = "00000000";

        const finalHex = downlinkTypeHex + daeHex + radioHex + superPerHex + spHex + pad;

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
            const sensorType = "general"; // General config can be used with any sensor
            window.location.href = `../downlinks.html?hexcode=${encodeURIComponent(hexcode)}&sensorType=${encodeURIComponent(sensorType)}`;
        });
    }

});
