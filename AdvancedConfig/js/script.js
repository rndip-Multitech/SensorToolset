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

