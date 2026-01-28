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
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

# Try to import the enhanced decoder from network-dashboard
try:
    import sys
    import os
    # Add the NetworkDashboard static/py directory to the path
    network_dashboard_py_path = os.path.join(os.path.dirname(__file__), 'NetworkDashboard-0.1', 'static', 'py')
    if network_dashboard_py_path not in sys.path:
        sys.path.insert(0, network_dashboard_py_path)
    from radiobridgev3 import Decoder
    ENHANCED_DECODER_AVAILABLE = True
    rb_decoder = Decoder()
except ImportError:
    ENHANCED_DECODER_AVAILABLE = False
    rb_decoder = None


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

        if message_type == 0x00:  # Reset Message
            decoded_message["reset_info"] = payload[:6].hex() if len(payload) >= 6 else payload.hex()
        elif message_type == 0x01:  # Supervisory Message
            battery_voltage_hex = format(payload[2], "02x") if len(payload) > 2 else "00"
            battery_voltage = int(battery_voltage_hex, 16) * 0.1
            decoded_message.update(
                {
                    "device_error_code": payload[0] if len(payload) > 0 else 0,
                    "current_sensor_state": payload[1] if len(payload) > 1 else 0,
                    "battery_voltage_hex": battery_voltage_hex,
                    "battery_voltage": battery_voltage,
                }
            )
        elif message_type == 0x03:  # Door/Window Sensor
            status = payload[0] if len(payload) > 0 else 0
            decoded_message.update(
                {
                    "open_close_status": "Open" if status == 0x00 else "Closed",
                }
            )
        elif message_type == 0x06:  # Push Button Sensor
            button_id = payload[0] if len(payload) > 0 else 0
            action = payload[1] if len(payload) > 1 else 0
            action_map = {0x00: "Button Pressed", 0x01: "Button Released", 0x02: "Button Hold"}
            decoded_message.update(
                {
                    "button_id": button_id,
                    "action_performed": action_map.get(action, f"Unknown ({action})"),
                }
            )
        elif message_type == 0x07:  # Dry Contact Sensor
            status = payload[0] if len(payload) > 0 else 0
            decoded_message.update(
                {
                    "connection_status": "Connected" if status == 0x00 else "Disconnected",
                }
            )
        elif message_type == 0x08:  # Water Leak Sensor
            decoded_message.update(
                {
                    "water_status": "Water present" if payload[0] == 0x00 else "Water not present",
                    "Measurement (0-255)": payload[1] if len(payload) > 1 else 0,
                }
            )
        elif message_type == 0x09:  # Thermistor Temperature Sensor
            event_type = payload[0] if len(payload) > 0 else 0
            integer_temp = payload[1] & 0x7F if len(payload) > 1 else 0
            sign_temp = (payload[1] & 0x80) >> 7 if len(payload) > 1 else 0
            integer_temp = integer_temp if sign_temp == 0 else -integer_temp
            decimal_temp = (payload[2] >> 4) / 10.0 if len(payload) > 2 else 0.0
            temperature_celsius = integer_temp + decimal_temp
            temperature_fahrenheit = (temperature_celsius * 9 / 5) + 32
            
            event_type_map = {
                0x00: "Periodic Report",
                0x01: "Temperature above upper threshold",
                0x02: "Temperature below lower threshold",
                0x03: "Temperature report-on-change increase",
                0x04: "Temperature report-on-change decrease",
            }
            decoded_message.update(
                {
                    "event_type": event_type_map.get(event_type, f"Unknown ({event_type})"),
                    "current_temperature": f"{temperature_fahrenheit:.1f} °F ({temperature_celsius:.1f} °C)",
                }
            )
        elif message_type == 0x0A:  # Tilt Sensor
            event_type = payload[0] if len(payload) > 0 else 0
            angle = payload[1] if len(payload) > 1 else 0
            
            event_type_map = {
                0x00: "Periodic Report",
                0x01: "Tilt angle above threshold",
                0x02: "Tilt angle below threshold",
                0x03: "Tilt angle report-on-change increase",
                0x04: "Tilt angle report-on-change decrease",
            }
            decoded_message.update(
                {
                    "event_type": event_type_map.get(event_type, f"Unknown ({event_type})"),
                    "angle_of_tilt": f"{angle}°",
                }
            )
        elif message_type == 0x0D:  # Temperature and Humidity Sensor
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
        
        # Use enhanced decoder if available, otherwise fall back to basic decoder
        if isinstance(data, dict) and "data" in data:
            if ENHANCED_DECODER_AVAILABLE and 'up' in topic and data.get('data'):
                try:
                    # Use the enhanced decoder from network-dashboard
                    decoded_bytes = base64.b64decode(data['data'])
                    rb_data_decoded = rb_decoder.decodePayload(data, decoded_bytes)
                    if rb_data_decoded:
                        data["data_decoded"] = rb_data_decoded
                        # Map event to message_type for compatibility
                        if "event" in rb_data_decoded:
                            event = rb_data_decoded["event"]
                            # Map event names to message types for sensor discovery
                            event_to_type = {
                                "water": "Water Leak Sensor",
                                "door_window": "Door/Window Sensor",
                                "push_button": "Push Button Sensor",
                                "contact": "Dry Contact Sensor",
                                "temperature": "Thermistor Temperature Sensor",
                                "tilt": "Tilt Sensor",
                                "air_temperature_humidity": "Temperature and Humidity Sensor",
                                "supervisory": "Supervisory Message",
                                "reset": "Reset Message",
                            }
                            message_type = event_to_type.get(event, event)
                        else:
                            message_type = None
                except Exception as e:
                    print(f"Enhanced decoder failed, using basic decoder: {e}")
                    data["data_decoded"] = decode_sensor_data(data["data"])
                    message_type = data["data_decoded"].get("message_type")
            else:
                # Use basic decoder
                data["data_decoded"] = decode_sensor_data(data["data"])
                message_type = data["data_decoded"].get("message_type")

            # Scrape DevEUI and sensor type for sensor discovery (any uplink with deveui)
            dev_eui = data.get("deveui")
            if dev_eui:
                sensor_type = "Other"
                if message_type and isinstance(message_type, str):
                    st = message_type.lower()
                    if not any(
                        unwanted in st
                        for unwanted in ("unknown", "supervisory message", "reset message", "downlink", "device_info", "link_quality")
                    ):
                        sensor_type = st
                existing = next((s for s in sensor_list if s.get("DevEUI") == dev_eui), None)
                if existing:
                    if sensor_type != "Other":
                        existing["sensor_type"] = sensor_type
                else:
                    sensor_list.append({"DevEUI": dev_eui, "sensor_type": sensor_type})
                    print(f"Discovered sensor: {dev_eui} ({sensor_type})")

        elif isinstance(data, dict):
            # No "data" payload (e.g. different broker format) – still discover by DevEUI
            dev_eui = data.get("deveui")
            if dev_eui and "up" in topic:
                existing = next((s for s in sensor_list if s.get("DevEUI") == dev_eui), None)
                if not existing:
                    sensor_list.append({"DevEUI": dev_eui, "sensor_type": "Other"})
                    print(f"Discovered sensor: {dev_eui} (Other)")

        # Add current timestamp
        if isinstance(data, dict):
            data['current_time'] = datetime.now().astimezone().isoformat()
        
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
    
    If 'hexcode' is provided in data (as base64), it will be used directly instead
    of constructing the message from form fields.
    """
    target_broker = broker_ip or current_broker_ip
    if not target_broker:
        return {"error": "No MQTT broker configured"}

    if "topic" not in data:
        return {"error": "Missing required key: 'topic'"}
    
    topic = data["topic"]
    
    # If hexcode or data (base64) is provided, use it directly (raw downlink)
    raw_base64 = data.get("hexcode") or data.get("data")
    if raw_base64 is not None:
        try:
            payload_obj = {"data": raw_base64 if isinstance(raw_base64, str) else raw_base64}
            if data.get("port") is not None:
                payload_obj["port"] = int(data["port"])
            payload = json.dumps(payload_obj)
            print(f"Publishing downlink to {topic} via {target_broker} (port={data.get('port')})")
            publish.single(topic, payload, hostname=target_broker)
            return {"message": "Downlink message sent successfully"}
        except Exception as e:
            return {"error": f"Error sending raw downlink: {str(e)}"}
    
    # Original logic: build downlink from form data
    if "sensor_type" not in data:
        return {"error": "Missing required key: 'sensor_type'"}

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
            mode = int(data["mode"], 16) if isinstance(data["mode"], str) and data["mode"].startswith("0x") else int(data["mode"])
            reporting_interval = int(data.get("reportingInterval", 10))
            
            # Handle both threshold mode (with separate temp/humidity restoral) and ROC mode
            if mode == 0x00:  # Threshold mode
                # For threshold mode, combine restoral margins (temp in lower 4 bits, humidity in upper 4 bits)
                restoral_margin_temp = int(data.get("restoralMarginTemp", 2))
                restoral_margin_humidity = int(data.get("restoralMarginHumidity", 5))
                restoral_margin = (restoral_margin_humidity << 4) | (restoral_margin_temp & 0x0F)
                
                lower_temp_threshold = int(data.get("lowerTempThreshold", 60))
                upper_temp_threshold = int(data.get("upperTempThreshold", 80))
                lower_humidity_threshold = int(data.get("lowerHumidityThreshold", 20))
                upper_humidity_threshold = int(data.get("upperHumidityThreshold", 80))
                
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
            elif mode == 0x01:  # Report-on-change mode
                temp_increase = int(data.get("tempIncrease", 2))
                temp_decrease = int(data.get("tempDecrease", 2))
                humidity_increase = int(data.get("humidityIncrease", 5))
                humidity_decrease = int(data.get("humidityDecrease", 5))
                
                downlink_message = [
                    0x0D,
                    mode,
                    reporting_interval,
                    0x00,  # Padding for restoral margin in ROC mode
                    temp_increase,
                    temp_decrease,
                    humidity_increase,
                    humidity_decrease,
                ]
            else:
                return {"error": f"Invalid mode value: {mode}"}
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


