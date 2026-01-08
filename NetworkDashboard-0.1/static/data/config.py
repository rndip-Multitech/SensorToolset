"""
Authors: Benjamin Lindeen, Austin Jacobson
This file is used to store lists of data which is received in the JSON messages from the MQTT broker.
"""

"""
List of abbreviations for data fields in the JSON messages.
"""
tooltips = {
    "ack": "Acknowledgment flag (true/false)",
    "adr": "Adaptive Data Rate (true/false)",
    "appeui": "Application EUI (Extended Unique Identifier)",
    "chan": "Channel number used for communication",
    "cls": "Class of the LoRa device (0 = Class A)",
    "codr": "Coding rate used for Forward Error Correction (FEC)",
    "data": "Payload data (Base64 encoded)",
    "data_decoded": "Decoded data from Base64 encoding",
    "datr": "Data rate and bandwidth (e.g., SF7BW125)",
    "devaddr": "Device address of the LoRaWAN node",
    "deveui": "Device EUI (Extended Unique Identifier)",
    "fcnt": "Frame counter incremented with each message",
    "foff": "Frequency offset in Hz",
    "freq": "Frequency in MHz",
    "gweui": "Gateway EUI (Extended Unique Identifier)",
    "joineui": "Join EUI (Extended Unique Identifier)",
    "jver": "Join version number",
    "lsnr": "Signal-to-Noise Ratio (SNR) in dB",
    "mhdr": "MAC header containing message type information",
    "mid": "Message ID for tracking",
    "modu": "Modulation scheme (e.g., LORA)",
    "opts": "Options field for MAC commands",
    "port": "Application port number",
    "rfch": "RF chain used for reception",
    "rssi": "Received Signal Strength Indicator (RSSI) in dBm",
    "rssis": "RSSI at the gateway in dBm",
    "seqn": "Sequence number of the message",
    "size": "Size of the payload in bytes",
    "stat": "Status of the received packet (1 = valid)",
    "time": "Timestamp of message reception (UTC)",
    "tmst": "Timestamp in microseconds since gateway start",
    "conductance": "Analog measurement of the conductance between probes (scale of 0-255)"
}

"""
List of hexcode values for the message types.
"""
message_type_map = {
    0x00: "Reset Message",
    0x01: "Supervisory Message",
    0x02: "Tamper Sensor",
    0x03: "Door/Window Sensor",
    0x06: "Push Button Sensor",
    0x07: "Dry Contact Sensor",
    0x08: "Water Leak Sensor",
    0x09: "Thermistor Temperature Sensor",
    0x0A: "Tilt Sensor",
    0x0D: "Temperature and Humidity Sensor",
    0x0E: "Accelerometer-based Movement Sensor",
    0x0F: "High-precision Tilt Sensor",
    0x10: "Ultrasonic Distance Sensor",
    0x11: "4-20mA Current Loop Sensor",
    0x13: "Thermocouple Temperature Sensor",
    0x14: "Voltmeter Sensor",
    0x19: "CMOS Temperature Sensor",
    0xFA: "Device Info Message",
    0xFB: "Link Quality Message",
    0xFF: "Downlink Received Acknowledgement Message",
}
