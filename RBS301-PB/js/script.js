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
    const enableButtonPressed = document.getElementById("enableButtonPressed");
    const enableButtonReleased = document.getElementById("enableButtonReleased");
    const enableButtonHold = document.getElementById("enableButtonHold");
    const holdDelayRow = document.getElementById("holdDelayRow");
    const holdDelay = document.getElementById("holdDelay");

    const ledDuringPress = document.getElementById("ledDuringPress");
    const ledAfterSend = document.getElementById("ledAfterSend");
    const ledAfterAck = document.getElementById("ledAfterAck");

    const generateButton = document.getElementById("generate-button");
    const hexSection = document.getElementById("hex-section");
    const hexOutput = document.getElementById("hex-output");

    const copyButton = document.getElementById("copy-button");
    const howButton = document.getElementById("how-button");


    /* ============================================================
       Generate Hex Code
    ============================================================ */
    generateButton.addEventListener("click", () => {
        const cPressed = enableButtonPressed.checked;
        const cReleased = enableButtonReleased.checked;
        const cHold = enableButtonHold.checked;

        // Downlink type for push button sensor
        const downlinkTypeHex = "06";

        // Calculate button event flags (characters 3-4)
        // Inverted bits: unchecked = 1
        // Bit 0 (1): Enable Button Pressed Event UNCHECKED
        // Bit 1 (2): Enable Button Released Event UNCHECKED
        // Bit 2 (4): Enable Button Hold Event UNCHECKED
        let buttonEventFlags = 0;
        if (!cPressed) buttonEventFlags += 1;
        if (!cReleased) buttonEventFlags += 2;
        if (!cHold) buttonEventFlags += 4;
        const buttonEventHex = buttonEventFlags.toString(16).padStart(2, '0').toUpperCase();

        // Hold delay (characters 5-6)
        const holdDelayHex = holdDelay.value;

        // Calculate LED flags (characters 7-8)
        // Inverted bits: unchecked = 1
        // Bit 0 (1): LED illumination during button press UNCHECKED
        // Bit 1 (2): Blink LED after send UNCHECKED
        // Bit 2 (4): Blink LED after message ACK received UNCHECKED
        let ledFlags = 0;
        if (!ledDuringPress.checked) ledFlags += 1;
        if (!ledAfterSend.checked) ledFlags += 2;
        if (!ledAfterAck.checked) ledFlags += 4;
        const ledFlagsHex = ledFlags.toString(16).padStart(2, '0').toUpperCase();

        // Padding
        const pad = "0000000000";

        // Build the full hexcode
        const fullHex = downlinkTypeHex + buttonEventHex + holdDelayHex + ledFlagsHex + pad;

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
