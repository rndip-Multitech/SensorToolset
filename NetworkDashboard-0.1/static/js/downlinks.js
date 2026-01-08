/**
 * Authors: Benjamin Lindeen, Austin Jacobson
 * @file downlinks.js
 * This file is used to handle the downlinks page functionality.
 * It contains the following functions:
 * - connectToBroker(event)
 * - sendDownlink(event)
 * - document.addEventListener('DOMContentLoaded', (event))
 */

let brokerIp = '';


/**
 * Function to fetch the sensors from the server and populate the sensor select dropdown
 * Also, show/hide the configuration based on the selected sensor type
 * Also, show/hide the configuration based on the selected mode
 * @param event - The event object
 * @returns {void}
 */
document.addEventListener('DOMContentLoaded', (event) => {
    const sensorSelectElement = document.getElementById('sensorSelect');
    const modeElement = document.getElementById('mode');
    const thresholdModeConfig = document.getElementById('thresholdModeConfig');
    const reportOnChangeConfig = document.getElementById('reportOnChangeConfig');

    fetch('/get_sensors')
        .then(response => response.json())
        .then(data => {
            console.log("Fetched sensors:", data.sensors);
            data.sensors.forEach(sensor => {
                const option = document.createElement('option');
                option.value = sensor.DevEUI;
                option.textContent = `${sensor.DevEUI} (${sensor.sensor_type})`;
                sensorSelectElement.appendChild(option);
            });
            // Trigger change event if only one sensor is present
            if (data.sensors.length === 1) {
                sensorSelectElement.dispatchEvent(new Event('change'));
            }
        })
        .catch(error => {
            console.error('Error fetching sensors:', error);
        });

    if (sensorSelectElement) {
        sensorSelectElement.addEventListener('change', (event) => {
            const selectedSensorText = sensorSelectElement.options[sensorSelectElement.selectedIndex].textContent;
            console.log("Selected sensor text:", selectedSensorText);
            const selectedSensorType = selectedSensorText.split('(')[1].split(')')[0].toLowerCase();
            console.log("Selected sensor type:", selectedSensorType);

            if (selectedSensorType.includes('water')) {
                document.getElementById('waterSensorConfig').style.display = 'block';
                document.getElementById('tempHumiditySensorConfig').style.display = 'none';
            } else if (selectedSensorType.includes('temperature') && selectedSensorType.includes('humidity')) {
                document.getElementById('waterSensorConfig').style.display = 'none';
                document.getElementById('tempHumiditySensorConfig').style.display = 'block';
            } else {
                document.getElementById('waterSensorConfig').style.display = 'none';
                document.getElementById('tempHumiditySensorConfig').style.display = 'none';
            }
        });
    }

    if (modeElement) {
        modeElement.addEventListener('change', (event) => {
            const mode = event.target.value;
            thresholdModeConfig.style.display = mode === '0x00' ? 'block' : 'none';
            reportOnChangeConfig.style.display = mode === '0x01' ? 'block' : 'none';
        });
    }

    document.querySelectorAll('.help-button').forEach(button => {
        button.addEventListener('click', (event) => {
            const modalId = event.target.getAttribute('data-modal');
            openHelpModal(modalId);
        });
    });

    window.onclick = function(event) {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        });
    }
});

/**
 * Function to connect to the MQTT broker
 * and subscribe to the given topic
 * Also, store the broker IP for downlink usage
 * @param event - The event object
 * @returns {void}
 */
function connectToBroker(event) {
    event.preventDefault();
    const broker = document.getElementById('broker').value;
    const port = document.getElementById('port').value;
    const topic = document.getElementById('topic').value;

    fetch('/connect', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({broker, port, topic})
    })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                alert(data.message);
                brokerIp = broker; // Store broker IP for downlink usage
            } else {
                alert('Failed to connect to the broker');
            }
        })
        .catch(error => {
            alert('Error: ' + error);
        });
}

/**
 * Function to send downlink data to the selected sensor
 * Also, construct the downlink data based on the selected sensor type
 * and send it to the server
 * @param event
 * @returns {void}
 */
function sendDownlink(event) {
    event.preventDefault();
    const sensorSelectElement = document.getElementById('sensorSelect');
    const sensorType = sensorSelectElement ? sensorSelectElement.options[sensorSelectElement.selectedIndex].text.split(' ')[1].toLowerCase() : null;
    const devEui = sensorSelectElement ? sensorSelectElement.value.replace(/-/g, '') : ''; // Remove dashes from DevEUI
    const topic = `lora/${devEui}/down`; // Construct the topic
    let downlinkData = {topic, sensor_type: sensorType};

    if (sensorType.includes('water')) {
        const enableWaterPresent = document.querySelector('input[name="enable_water_present"]:checked').value;
        const enableWaterNotPresent = document.querySelector('input[name="enable_water_not_present"]:checked').value;
        const threshold = document.getElementById('threshold').value;
        const restoral = document.getElementById('restoral').value;
        downlinkData = {
            ...downlinkData,
            enableWaterPresent,
            enableWaterNotPresent,
            threshold,
            restoral
        };
    } else if (sensorType.includes('temperature') && sensorType.includes('humidity')) {
        const mode = document.getElementById('mode').value;
        if (mode === '0x00') {
            const reportingInterval = document.getElementById('reportingInterval').value;
            const restoralMarginTemp = document.getElementById('restoralMarginTemp').value;
            const lowerTempThreshold = document.getElementById('lowerTempThreshold').value;
            const upperTempThreshold = document.getElementById('upperTempThreshold').value;
            const restoralMarginHumidity = document.getElementById('restoralMarginHumidity').value;
            const lowerHumidityThreshold = document.getElementById('lowerHumidityThreshold').value;
            const upperHumidityThreshold = document.getElementById('upperHumidityThreshold').value;
            downlinkData = {
                ...downlinkData,
                mode,
                reportingInterval,
                restoralMarginTemp,
                lowerTempThreshold,
                upperTempThreshold,
                restoralMarginHumidity,
                lowerHumidityThreshold,
                upperHumidityThreshold
            };
        } else if (mode === '0x01') {
            const tempIncrease = document.getElementById('tempIncrease').value;
            const tempDecrease = document.getElementById('tempDecrease').value;
            const humidityIncrease = document.getElementById('humidityIncrease').value;
            const humidityDecrease = document.getElementById('humidityDecrease').value;
            downlinkData = {
                ...downlinkData,
                mode,
                tempIncrease,
                tempDecrease,
                humidityIncrease,
                humidityDecrease
            };
        }
    }

    console.log("Sending downlink data:", JSON.stringify(downlinkData, null, 2)); // Debug log

    fetch('/send_downlink', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(downlinkData)
    })
        .then(response => response.json())
        .then(data => {
            console.log('Response data:', data); // Debug log
            if (data.message) {
                alert('Downlink sent: ' + data.message);
            } else {
                alert('Error sending downlink: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error sending downlink: ' + error);
        });
}

function openHelpModal(modalId) {
    const helpModal = document.getElementById(modalId);
    if (helpModal) {
        helpModal.style.display = 'block';
    }
}

function closeHelpModal(modalId) {
    const helpModal = document.getElementById(modalId);
    if (helpModal) {
        helpModal.style.display = 'none';
    }
}

// Add the existing function to close the modal when clicking outside of it
window.onclick = function(event) {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    });
};
