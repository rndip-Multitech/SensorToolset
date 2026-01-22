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
       Element References
    ============================================================ */
    const tiltAxisWidth = document.getElementById("tiltAxisWidth");
    const enableTransitionsVertical = document.getElementById("enableTransitionsVertical");
    const enableTransitionsHorizontal = document.getElementById("enableTransitionsHorizontal");
    const enableRocHorizontalChk = document.getElementById("enableRocHorizontal");
    const enableRocVerticalChk = document.getElementById("enableRocVertical");
    const angleVerticalRow = document.getElementById("angleVerticalRow");
    const angleVerticalSelect = document.getElementById("angleVerticalSelect");
    const angleHorizontalRow = document.getElementById("angleHorizontalRow");
    const angleHorizontalSelect = document.getElementById("angleHorizontalSelect");
    const rocHorizontalRow = document.getElementById("rocHorizontalRow");
    const rocHorizontalSelect = document.getElementById("rocHorizontalSelect");
    const rocVerticalRow = document.getElementById("rocVerticalRow");
    const rocVerticalSelect = document.getElementById("rocVerticalSelect");
    const verticalHoldTime = document.getElementById("verticalHoldTime");
    const horizontalHoldTime = document.getElementById("horizontalHoldTime");

    const aboutAxisBtn = document.getElementById("about-axis-button");
    const aboutHoldtimeBtn = document.getElementById("about-holdtime-button");

    const generateButton = document.getElementById("generate-button");
    const hexSection = document.getElementById("hex-section");
    const hexOutput = document.getElementById("hex-output");

    const copyButton = document.getElementById("copy-button");
    const howButton = document.getElementById("how-button");


    /* ============================================================
       Show/Hide Angle for Vertical Transition
    ============================================================ */
    enableTransitionsVertical.addEventListener("change", () => {
        angleVerticalRow.style.display = enableTransitionsVertical.checked ? "flex" : "none";
    });


    /* ============================================================
       Show/Hide Angle for Horizontal Transition
    ============================================================ */
    enableTransitionsHorizontal.addEventListener("change", () => {
        angleHorizontalRow.style.display = enableTransitionsHorizontal.checked ? "flex" : "none";
    });


    /* ============================================================
       Show/Hide Report-on-Change Toward Horizontal
    ============================================================ */
    enableRocHorizontalChk.addEventListener("change", () => {
        rocHorizontalRow.style.display = enableRocHorizontalChk.checked ? "flex" : "none";
    });


    /* ============================================================
       Show/Hide Report-on-Change Toward Vertical
    ============================================================ */
    enableRocVerticalChk.addEventListener("change", () => {
        rocVerticalRow.style.display = enableRocVerticalChk.checked ? "flex" : "none";
    });


    /* ============================================================
       About Tilt Axis Settings
    ============================================================ */
    aboutAxisBtn.addEventListener("click", () => {
        showDialog(
            "Tilt Axis Width/Length configures the sensor axis mode.\n\nRefer to the RadioBridge documentation for specific values."
        );
    });


    /* ============================================================
       About Hold Times
    ============================================================ */
    aboutHoldtimeBtn.addEventListener("click", () => {
        showDialog(
            "Hold times specify how long the sensor must remain in a position before reporting a state change.\n\nVertical Hold Time: Time the sensor must be vertical before reporting.\n\nHorizontal Hold Time: Time the sensor must be horizontal before reporting.\n\nValid range: 0-255"
        );
    });


    /* ============================================================
       Generate Hex Code
    ============================================================ */
    generateButton.addEventListener("click", () => {
        // Characters 1-2: Downlink_Message_Type (always "0A")
        const downlinkType = "0A";

        // Character 3: Tilt_Axis-Width/Length
        const axisWidth = tiltAxisWidth.value;

        // Character 4: Disable/Enable_Tilts (calculated from checkboxes as inverted bits)
        // Bit 0 (1): Enable transitions to horizontal orientation UNCHECKED
        // Bit 1 (2): Enable transitions to vertical orientation UNCHECKED
        // Bit 2 (4): Enable report-on-change toward horizontal UNCHECKED
        // Bit 3 (8): Enable report-on-change toward vertical UNCHECKED
        let enableTiltsValue = 0;
        if (!enableTransitionsHorizontal.checked) enableTiltsValue += 1;
        if (!enableTransitionsVertical.checked) enableTiltsValue += 2;
        if (!enableRocHorizontalChk.checked) enableTiltsValue += 4;
        if (!enableRocVerticalChk.checked) enableTiltsValue += 8;
        const enableTilts = enableTiltsValue.toString(16).toUpperCase();

        // Characters 5-6: Angle_for_Transition_to_Horizontal_state
        const angleHorizHex = enableTransitionsHorizontal.checked ? angleHorizontalSelect.value : "00";

        // Characters 7-8: Angle_for_Transition_to_Vert_state
        const angleVertHex = enableTransitionsVertical.checked ? angleVerticalSelect.value : "00";

        // Characters 9-10: Vertical_Hold_Time
        const vertHoldHex = verticalHoldTime.value;

        // Characters 11-12: Horizontal_Hold_Time
        const horizHoldHex = horizontalHoldTime.value;

        // Characters 13-14: Report-on-change_Toward_Horizontal_Degrees
        const rocHorizHex = enableRocHorizontalChk.checked ? rocHorizontalSelect.value : "00";

        // Characters 15-16: Report-on-change_Toward_Vertical_Degrees
        const rocVertHex = enableRocVerticalChk.checked ? rocVerticalSelect.value : "00";

        // Build the full hexcode
        const fullHex = downlinkType + axisWidth + enableTilts + angleHorizHex + angleVertHex + vertHoldHex + horizHoldHex + rocHorizHex + rocVertHex;

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
            "1. Copy the generated hex string.\n2. Paste it into your LoRaWAN server or gateway downlink tool. For MultiTech gateways, open the gateway mPower web interface, choose LoRaWAN, Downlink Queue. Choose Add New, then paste the hexcode into the Data input box. Set Ack Attempts to 2 and Rx Window to 2.\n3. Send the downlink to your RadioBridge sensor.\n4. The sensor applies the configuration the next time it sends an uplink."
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
            const sensorType = "tilt sensor";
            window.location.href = `../downlinks.html?hexcode=${encodeURIComponent(hexcode)}&sensorType=${encodeURIComponent(sensorType)}`;
        });
    }

});
