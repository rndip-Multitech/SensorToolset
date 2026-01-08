"""
RadioBridge Tools MQTT utilities

This module connects to the local LoRa Network Server's MQTT broker on a
MultiTech mPower gateway and:
- Subscribes to uplink topics (e.g. 'lora/+/up') to discover active sensors
- Decodes payloads to identify sensor type
- Sends downlink messages on 'lora/<DEV-EUI>/down' topics

Based on the MQTT message format documented by MultiTech:
See: https://www.multitech.net/developer/software/lora/lora-network-server/mqtt-messages/
"""

import base64
import json
from typing import Any, Dict, List

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish


# Minimal copy of the message_type_map so we don't depend on the
# NetworkDashboard package structure.
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


message_buffer: List[Dict[str, Any]] = []
sensor_list: List[Dict[str, str]] = []

# Single global client; we run it in loop_start() mode
mqtt_client: mqtt.Client | None = None
current_broker_ip: str | None = None


def decode_temp_humidity_sensor(payload: bytes) -> Dict[str, Any]:
    try:
        reporting_event_type = payload[0]
        integer_temp = payload[1] & 0x7F
        sign_temp = (payload[1] & 0x80) >> 7
        integer_temp = integer_temp if sign_temp == 0 else -integer_temp
        decimal_temp = (payload[2] >> 4) / 10.0
        temperature_celsius = integer_temp + decimal_temp

        temperature_fahrenheit = (temperature_celsius * 9 / 5) + 32

        integer_humidity = payload[3]
        decimal_humidity = (payload[4] >> 4) / 10.0
        humidity = integer_humidity + decimal_humidity

        return {
            "reporting_event_type": reporting_event_type,
            "temperature_celsius": temperature_celsius,
            "temperature_fahrenheit": temperature_fahrenheit,
            "humidity": humidity,
        }
    except (IndexError, ValueError) as e:
        return {"error": f"Error decoding temperature and humidity sensor payload: {e}"}


def decode_sensor_data(data: str) -> Dict[str, Any]:
    padding = "=" * ((4 - len(data) % 4) % 4)
    base64_data_padded = data + padding

    try:
        decoded_bytes = base64.b64decode(base64_data_padded)
        protocol_version = decoded_bytes[0] >> 4
        packet_counter = decoded_bytes[0] & 0x0F
        message_type = decoded_bytes[1]
        payload = decoded_bytes[2:]

        decoded_message: Dict[str, Any] = {
            "protocol_version": protocol_version,
            "packet_counter": packet_counter,
            "message_type": message_type_map.get(message_type, f"Unknown ({message_type})"),
        }

        if message_type == 0x08:
            decoded_message.update(
                {
                    "water_status": "Water present" if payload[0] == 0x00 else "Water not present",
                    "Measurement (0-255)": payload[1],
                }
            )
        elif message_type == 0x00:
            decoded_message["reset_info"] = payload[:6].hex()
        elif message_type == 0x01:
            battery_voltage_hex = format(payload[2], "02x")
            battery_voltage = int(battery_voltage_hex) * 0.1
            decoded_message.update(
                {
                    "device_error_code": payload[0],
                    "current_sensor_state": payload[1],
                    "battery_voltage_hex": battery_voltage_hex,
                    "battery_voltage": battery_voltage,
                }
            )
        elif message_type == 0x0D:
            decoded_message["data"] = decode_temp_humidity_sensor(payload)
        else:
            decoded_message["payload"] = payload.hex()

        return decoded_message
    except (base64.binascii.Error, IndexError, ValueError) as e:
        return {"error": f"Error decoding Base64 or interpreting the payload: {e}"}


def _on_connect(client: mqtt.Client, userdata: Dict[str, Any], flags, rc: int) -> None:
    print(f"MQTT connected with result code {rc}")
    topic = userdata.get("topic", "lora/+/up")
    client.subscribe(topic)


def _on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    global message_buffer, sensor_list
    topic = msg.topic
    message = msg.payload.decode()
    print(f"Received MQTT message on {topic}: {message}")
    try:
        data = json.loads(message)
        if isinstance(data, dict) and "data" in data:
            data["data_decoded"] = decode_sensor_data(data["data"])

            # Scrape DevEUI and sensor type
            dev_eui = data.get("deveui")
            message_type = data["data_decoded"].get("message_type")

            if dev_eui and isinstance(message_type, str):
                sensor_type = message_type.lower()
                if not any(
                    unwanted in sensor_type
                    for unwanted in ("unknown", "supervisory message", "reset message", "downlink")
                ):
                    sensor_entry = {"DevEUI": dev_eui, "sensor_type": sensor_type}
                    if sensor_entry not in sensor_list:
                        sensor_list.append(sensor_entry)
                        print(f"Discovered sensor: {sensor_entry}")

        message_buffer.append({"type": "json", "topic": topic, "data": data})
    except json.JSONDecodeError:
        message_buffer.append({"type": "text", "topic": topic, "data": message})
    except Exception as e:  # noqa: BLE001
        print(f"Error processing MQTT message: {e}")
        message_buffer.append(
            {"type": "error", "topic": topic, "data": f"Error processing message: {e}"}
        )

    if len(message_buffer) > 150:
        message_buffer.pop(0)


def connect_to_broker(broker: str = "localhost", port: int = 1883, topic: str = "lora/+/up") -> None:
    """
    Connect to the MQTT broker and subscribe to uplink messages.

    The default topic 'lora/+/up' follows the MultiTech LoRa Network Server
    MQTT documentation: https://www.multitech.net/developer/software/lora/lora-network-server/mqtt-messages/
    """
    global mqtt_client, current_broker_ip

    current_broker_ip = broker

    if mqtt_client is None:
        client = mqtt.Client()
        client.user_data_set({"topic": topic})
        client.on_connect = _on_connect
        client.on_message = _on_message
        client.connect(broker, int(port), 60)
        client.loop_start()
        mqtt_client = client
    else:
        # Update subscription/topic if already connected
        mqtt_client.user_data_set({"topic": topic})
        mqtt_client.subscribe(topic)


def get_sensors() -> List[Dict[str, str]]:
    """Return the list of discovered sensors."""
    return sensor_list


def get_messages() -> List[Dict[str, Any]]:
    """Return the buffered MQTT messages."""
    return message_buffer


def send_downlink(data: Dict[str, Any], broker_ip: str | None = None) -> Dict[str, Any]:
    """
    Construct and publish a downlink packet for supported sensor types.

    The payload is published to 'lora/<DEV-EUI>/down' as JSON with a base64-encoded
    'data' field, matching the examples in the MultiTech documentation:
    https://www.multitech.net/developer/software/lora/lora-network-server/mqtt-messages/
    """
    target_broker = broker_ip or current_broker_ip
    if not target_broker:
        return {"error": "No MQTT broker configured"}

    if "topic" not in data or "sensor_type" not in data:
        return {"error": "Missing required keys: 'topic' or 'sensor_type'"}

    topic = data["topic"]
    sensor_type = data["sensor_type"]

    downlink_message: list[int] = []

    try:
        if "water" in sensor_type:
            enable_water_present = int(data["enableWaterPresent"])
            enable_water_not_present = int(data["enableWaterNotPresent"])
            threshold = int(data["threshold"])
            restoral = int(data["restoral"])
            enable_events = ((not enable_water_present) << 1) | (not enable_water_not_present)

            downlink_message = [
                0x08,  # Water sensor event
                enable_events,
                threshold,
                restoral,
                0x00,
                0x00,
                0x00,
                0x00,  # Padding with zeros
            ]
        elif "temperature" in sensor_type and "humidity" in sensor_type:
            mode = int(data["mode"], 16)
            reporting_interval = int(data["reportingInterval"])
            restoral_margin = int(data["restoralMargin"])
            lower_temp_threshold = int(data["lowerTempThreshold"])
            upper_temp_threshold = int(data["upperTempThreshold"])
            lower_humidity_threshold = int(data["lowerHumidityThreshold"])
            upper_humidity_threshold = int(data["upperHumidityThreshold"])
            downlink_message = [
                0x0D,  # Air Temperature and Humidity sensor configuration
                mode,
                reporting_interval,
                restoral_margin,
                lower_temp_threshold,
                upper_temp_threshold,
                lower_humidity_threshold,
                upper_humidity_threshold,
            ]
        else:
            return {"error": f"Unsupported sensor_type '{sensor_type}' for automatic encoding"}

        downlink_message_base64 = base64.b64encode(bytes(downlink_message)).decode("utf-8")
        payload = json.dumps({"data": downlink_message_base64})

        print(f"Publishing downlink to {topic} via {target_broker}: {payload}")
        publish.single(topic, payload, hostname=target_broker)
        return {"message": "Downlink message sent successfully"}
    except KeyError as e:
        return {"error": f"Missing key in downlink data: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


