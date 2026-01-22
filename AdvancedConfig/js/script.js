function generateHexcode() {
    // Get Link Quality Check values
    const linkQualityPeriod = document.getElementById('linkQualityPeriod').value;
    const linkQualityTimeValue = parseInt(document.getElementById('linkQualityTimeValue').value);
    
    // Calculate the fourth byte based on period selection
    let linkQualityValue;
    if (linkQualityPeriod === 'minutes') {
        linkQualityValue = linkQualityTimeValue + 128;
    } else {
        linkQualityValue = linkQualityTimeValue;
    }
    
    // Convert to hex and pad with leading "0" if result is one character
    let linkQualityHex = linkQualityValue.toString(16).toUpperCase();
    if (linkQualityHex.length === 1) {
        linkQualityHex = '0' + linkQualityHex;
    }
    
    // Build the hexcode: FC0001 + linkQualityHex + 00000000
    const hexcode = 'FC0001' + linkQualityHex + '00000000';
    
    // Display the result
    document.getElementById('hex-output').textContent = hexcode;
    document.getElementById('hex-section').style.display = 'block';
    document.getElementById('copy-button').style.display = 'inline-block';
}

function copyHexcode() {
    const hexcode = document.getElementById('hex-output').textContent;
    navigator.clipboard.writeText(hexcode).then(function() {
        alert('Hexcode copied to clipboard!');
    });
}

function scheduleDownlink() {
    const hexcode = document.getElementById('hex-output').textContent;
    if (!hexcode) {
        alert('Please generate a hexcode first.');
        return;
    }
    // Redirect to downlinks page with hexcode and sensor type
    const sensorType = "advanced"; // Advanced config can be used with any sensor
    window.location.href = `../downlinks.html?hexcode=${encodeURIComponent(hexcode)}&sensorType=${encodeURIComponent(sensorType)}`;
}

// Show schedule button when hexcode is generated
const originalGenerateHexcode = generateHexcode;
generateHexcode = function() {
    originalGenerateHexcode();
    const scheduleButton = document.getElementById('schedule-button');
    if (scheduleButton) {
        scheduleButton.style.display = 'inline-block';
    }
};
