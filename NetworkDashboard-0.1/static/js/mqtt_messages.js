/**
 * Authors: Benjamin Lindeen, Austin Jacobson
 * @file mqtt_messages.js
 * This file contains the JavaScript code for the MQTT messages page.
 * It contains the following functions:
 * - connectToBroker(event)
 * - fetchMessages(filter = '')
 * - showModal(data)
 * - closeModal()
 * - startFetchingMessages()
 * - dumpMessagesToJSON()
 * - document.querySelector('.close').addEventListener('click', closeModal)
 */

/**
 * Function to connect to the MQTT broker
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
                startFetchingMessages();
            } else {
                alert('Failed to connect to the broker');
            }
        })
        .catch(error => {
            alert('Error: ' + error);
        });
}

/**
 * Function to fetch messages from the server
 * and display them in the table
 * @param filter - The filter to apply to the messages
 * @returns {void}
 */
function fetchMessages(filter = '') {
    let currentPath = window.location.pathname;
    let endpoint = (currentPath === '/mqtt_messages') ? 'messages' : (currentPath === '/upload_messages') ? 'upload' : 'default';
    let currentURL = `${window.location.origin}/${endpoint}?filter=${filter}`;

    /**
     * Fetch the messages from the server
     * creates a table row for each message
     * and appends it to the table
     * @param currentURL - The URL to fetch the messages from
     */
    fetch(currentURL)
        .then(response => response.json())
        .then(data => {
            const messageTable = document.getElementById('messageTableBody');
            messageTable.innerHTML = '';
            data.messages.reverse();
            data.messages.forEach((message, index) => {
                const row = document.createElement('tr');
                const timeCell = document.createElement('td');
                const devEUICell = document.createElement('td');
                const topicCell = document.createElement('td');
                const messageTypeCell = document.createElement('td');
                const messageData1Cell = document.createElement('td');
                const messageData2Cell = document.createElement('td');
                const messageData3Cell = document.createElement('td');
                const buttonCell = document.createElement('td');
                const moreInfoButton = document.createElement('button');
                const gptButton = document.createElement('button');

                const time = message.data.time;
                const date = new Date(time);
                const options = {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    timeZoneName: 'short'
                };

                timeCell.textContent = date.toLocaleDateString('en-US', options);
                devEUICell.textContent = message.data.deveui;
                topicCell.textContent = message.topic.substring(message.topic.lastIndexOf('/') + 1);

                /**
                 * Check if the message type is 'json'
                 * checks for which type of sensor the JSON has data for
                 * and displays the data in the table
                 * @param message - The message object
                 */
                if (message.type === 'json') {
                    if ('data_decoded' in message.data) {
                        if ('message_type' in message.data.data_decoded) {
                            messageTypeCell.textContent = message.data.data_decoded.message_type;
                            data = message.data.data_decoded;
                        }
                        switch (data.message_type) {
                            case 'Water Leak Sensor':
                                messageData1Cell.innerHTML = `<em>Water Status:</em> <strong>${data.water_status}</strong><br>`;
                                messageData2Cell.innerHTML = `<em>Measurement (0-255):</em> <strong>${data['Measurement (0-255)']}</strong><br>`;
                                break;
                            case 'Door/Window Sensor Event':
                                messageData1Cell.innerHTML = `<em>Status:</em> <strong>${data.open_close_status}</strong><br>`;
                                break;
                            case 'Push Button Sensor':
                                messageData1Cell.innerHTML = `<em>Button ID:</em> <strong>${data.button_id}</strong><br>`;
                                messageData2Cell.innerHTML = `<em>Action Performed:</em> <strong>${data.action_performed}</strong><br>`;
                                break;
                            case 'Dry Contact Sensor':
                                messageData1Cell.innerHTML = `<em>Connection Status:</em> <strong>${data.connection_status}</strong><br>`;
                                break;
                            case 'Thermistor Temperature Sensor':
                                messageData1Cell.innerHTML = `<em>Event Type:</em> <strong>${data.event_type}</strong><br>`;
                                messageData2Cell.innerHTML = `<em>Temperature:</em> <strong>${data.current_temperature}</strong><br>`;
                                break;
                            case 'Tilt Sensor':
                                messageData1Cell.innerHTML = `<em>Event Type:</em> <strong>${data.event_type}</strong><br>`;
                                messageData2Cell.innerHTML = `<em>Angle of Tilt:</em> <strong>${data.angle_of_tilt}</strong><br>`;
                                break;
                            case 'Temperature and Humidity Sensor':
                                const eventTypeDescription = eventTypeMap[data.data.reporting_event_type] || `Unknown (${data.data.reporting_event_type})`;
                                messageData1Cell.innerHTML = `<em>Event Type:</em> <strong>${eventTypeDescription}</strong><br>`;
                                messageData2Cell.innerHTML = `<em>Temperature:</em> <strong>${data.data.temperature_fahrenheit.toFixed(2)} °F</strong><br>`;
                                messageData3Cell.innerHTML = `<em>Humidity:</em> <strong>${data.data.humidity}%</strong><br>`;
                                break;
                            case 'Supervisory Message':
                                messageData1Cell.innerHTML = `<em>Battery Voltage:</em> <strong>${data.battery_voltage.toFixed(1)}V</strong><br>`;
                                messageData2Cell.innerHTML = `<em>Error Code:</em> <strong>${data.device_error_code}</strong><br>`;
                                messageData3Cell.innerHTML = `<em>Sensor State:</em> <strong>${data.current_sensor_state}<strong><br>`;
                                break;
                        }
                    }
                    /**
                     * Create a button to show the full JSON data
                     * and a button to ask GPT for a response
                     * @param message - The message object
                     */
                    moreInfoButton.textContent = 'Full Json';
                    moreInfoButton.onclick = () => showModal(message.data);
                    buttonCell.appendChild(moreInfoButton);
                    gptButton.textContent = 'Ask gpt';
                    gptButton.onclick = () => {
                        fetch('/gpt', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(message.data)
                        })
                            .then(response => response.text())
                            .then(data => {
                                window.location.href = `/gpt_response?message=${encodeURIComponent(data)}`;
                            });
                    };
                    buttonCell.appendChild(gptButton);
                }

                row.appendChild(timeCell);
                row.appendChild(devEUICell);
                row.appendChild(topicCell);
                row.appendChild(messageTypeCell);
                row.appendChild(messageData1Cell);
                row.appendChild(messageData2Cell);
                row.appendChild(messageData3Cell);
                row.appendChild(buttonCell);
                messageTable.appendChild(row);
            });
        });
}

/**
 * Map of event types for the Temperature and Humidity Sensor
 * @type {{0: string, 1: string, 2: string, 3: string, 4: string, 5: string, 6: string, 7: string, 8: string}}
 */
const eventTypeMap = {
    0x00: "Periodic Report",
    0x01: "Temperature has risen above upper threshold",
    0x02: "Temperature has fallen below lower threshold",
    0x03: "Temperature report-on-change increase",
    0x04: "Temperature report-on-change decrease",
    0x05: "Humidity has risen above upper threshold",
    0x06: "Humidity has fallen below lower threshold",
    0x07: "Humidity report-on-change increase",
    0x08: "Humidity report-on-change decrease"
};

/**
 * Function to show the modal with the given data
 * @param data - The data to show in the modal
 * @returns {void}
 */
function showModal(data) {
    const modal = document.getElementById('myModal');
    const modalContent = document.getElementById('modalText');
    modalContent.textContent = JSON.stringify(data, null, 2);
    modal.style.display = 'block';
}

/**
 * Function to close the modal
 * @returns {void}
 */
function closeModal() {
    const modal = document.getElementById('myModal');
    modal.style.display = 'none';
}

/**
 * Function to start fetching messages every 5 seconds
 * @returns {void}
 */
function startFetchingMessages() {
    setInterval(() => fetchMessages(document.getElementById('filter').value), 5000);
}

/**
 * Close the modal when the user clicks the close button
 * @returns {void}
 */
document.querySelector('.close').addEventListener('click', closeModal);

/**
 * Close the modal when the user clicks outside of it
 * @returns {void}
 */
window.addEventListener('click', (event) => {
    const modal = document.getElementById('myModal');
    if (event.target === modal) {
        closeModal();
    }
});

/**
 * Dump messages to JSON
 * @returns {void}
 */
function dumpMessagesToJSON() {
    window.location.href = '/dump_messages';
}

/**
 * Dump messages to JSON when the button is clicked
 */
document.getElementById('dumpMessages').addEventListener('click', dumpMessagesToJSON);
