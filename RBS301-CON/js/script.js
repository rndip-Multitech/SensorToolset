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
    const notifyClose = document.getElementById("notifyClose");
    const notifyOpen  = document.getElementById("notifyOpen");

    const closeTime        = document.getElementById("closeTime");
    const closeTimeContainer = document.getElementById("closeTimeContainer");

    const openTime         = document.getElementById("openTime");
    const openTimeContainer  = document.getElementById("openTimeContainer");

    const aboutContactBtn = document.getElementById("about-contact-button");

    const generateButton = document.getElementById("generate-button");
    const hexSection     = document.getElementById("hex-section");
    const hexOutput      = document.getElementById("hex-output");

    const copyButton = document.getElementById("copy-button");
    const howButton  = document.getElementById("how-button");


    /* ============================================================
       Show/Hide Hold Time Containers
    ============================================================ */
    notifyClose.addEventListener("change", () => {
        closeTimeContainer.style.display =
            notifyClose.checked ? "inline-flex" : "none";
    });

    notifyOpen.addEventListener("change", () => {
        openTimeContainer.style.display =
            notifyOpen.checked ? "inline-flex" : "none";
    });

    // initial state
    closeTimeContainer.style.display = notifyClose.checked ? "inline-flex" : "none";
    openTimeContainer.style.display  = notifyOpen.checked  ? "inline-flex" : "none";


    /* ============================================================
       About Contact Settings
    ============================================================ */
    aboutContactBtn.addEventListener("click", () => {
        showDialog(
            "You can choose to be notified any time the contact is open or closed.\n\n" +
            "The hold-time values determine how long the sensor must remain in a " +
            "given state (open or closed) before sending a message. If set to zero, " +
            "a state-change message is sent immediately whenever the contact toggles."
        );
    });


    /* ============================================================
       Generate Hex Code
       Format:
           07  +  close/open hex  +  closeTimeHex  +  openTimeHex  +  0000
    ============================================================ */
    generateButton.addEventListener("click", () => {
        const cClose = notifyClose.checked;
        const cOpen  = notifyOpen.checked;

        if (!cClose && !cOpen) {
            showDialog(
                "Please enable at least one of the following:\n" +
                "- Send Notification on Contact Close\n" +
                "- Send Notification on Contact Open"
            );
            return;
        }

        let closeOpenHex = "03";     // 03 = neither, but prevented above

        if (cClose && cOpen) closeOpenHex = "00";
        else if (!cClose && cOpen) closeOpenHex = "01";
        else if (cClose && !cOpen) closeOpenHex = "02";

        const closeTimeHex = cClose ? closeTime.value : "0000";
        const openTimeHex  = cOpen  ? openTime.value  : "0000";

        const downlinkTypeHex = "07";
        const pad = "0000";

        const fullHex =
            downlinkTypeHex +
            closeOpenHex +
            closeTimeHex +
            openTimeHex +
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
