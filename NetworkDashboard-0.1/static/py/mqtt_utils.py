"""
Authors: Benjamin Lindeen, Austin Jacobson
This file contains functions to decode the payload received from the sensor and to send downlink messages to the sensor.
This file is used by and called by server.py.
"""

"""
Importing the required libraries.
"""
import paho.mqtt.client as mqtt
import base64
import json
import paho.mqtt.publish as publish
from static.data.config import message_type_map

message_buffer = []
mqtt_client = mqtt.Client()
sensor_list = []

"""
Following functions are used to decode the payload received from the temperature and humidity sensor.
"""


def decode_temp_humidity_sensor(payload):
    try:
        reporting_event_type = payload[0]
        integer_temp = payload[1] & 0x7F  # Mask to get the 7 bits of integer part
        sign_temp = (payload[1] & 0x80) >> 7  # Get the sign bit
        integer_temp = integer_temp if sign_temp == 0 else -integer_temp  # Apply sign
        decimal_temp = (payload[2] >> 4) / 10.0  # Get the upper 4 bits and divide by 10 to get decimal part
        temperature_celsius = integer_temp + decimal_temp

        # Convert to Fahrenheit
        temperature_fahrenheit = (temperature_celsius * 9 / 5) + 32

        integer_humidity = payload[3]
        decimal_humidity = (payload[4] >> 4) / 10.0  # Get the upper 4 bits and divide by 10 to get decimal part
        humidity = integer_humidity + decimal_humidity

        decoded_data = {
            'reporting_event_type': reporting_event_type,
            'temperature_celsius': temperature_celsius,
            'temperature_fahrenheit': temperature_fahrenheit,
            'humidity': humidity
        }

        return decoded_data
    except (IndexError, ValueError) as e:
        return {"error": f"Error decoding temperature and humidity sensor payload: {e}"}


"""
Following function is used to decode the payload received from the sensor.
"""


def decode_sensor_data(data):
    padding = '=' * ((4 - len(data) % 4) % 4)
    base64_data_padded = data + padding

    try:
        decoded_bytes = base64.b64decode(base64_data_padded)
        protocol_version = decoded_bytes[0] >> 4
        packet_counter = decoded_bytes[0] & 0x0F
        message_type = decoded_bytes[1]
        payload = decoded_bytes[2:]

        decoded_message = {
            'protocol_version': protocol_version,
            'packet_counter': packet_counter,
            'message_type': message_type_map.get(message_type, f"Unknown ({message_type})")
        }

        if message_type == 0x08:
            decoded_message.update({
                'water_status': 'Water present' if payload[0] == 0x00 else 'Water not present',
                'Measurement (0-255)': payload[1]
            })
        elif message_type == 0x00:
            decoded_message['reset_info'] = payload[:6].hex()
        elif message_type == 0x01:
            battery_voltage_hex = format(payload[2], '02x')
            battery_voltage = int(battery_voltage_hex) * 0.1
            decoded_message.update({
                'device_error_code': payload[0],
                'current_sensor_state': payload[1],
                'battery_voltage_hex': battery_voltage_hex,
                'battery_voltage': battery_voltage
            })
        elif message_type == 0x0D:
            decoded_message['data'] = decode_temp_humidity_sensor(payload)
        else:
            decoded_message['payload'] = payload.hex()

        return decoded_message
    except (base64.binascii.Error, IndexError, ValueError) as e:
        return {"error": f"Error decoding Base64 or interpreting the payload: {e}"}


"""
Following functions are used to connect to the MQTT broker and subscribe to the topic.
"""


def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    client.subscribe(userdata['topic'])


def on_message(client, userdata, msg):
    global message_buffer, sensor_list
    topic = msg.topic
    message = msg.payload.decode()
    print(f"Received message: {message}")
    try:
        data = json.loads(message)
        if isinstance(data, dict) and 'data' in data:
            data['data_decoded'] = decode_sensor_data(data['data'])
            if "error" in data['data_decoded']:
                print(data['data_decoded']["error"])
            else:
                print(f"Decoded data: {data['data_decoded']}")

                # Scrape DevEUI and sensor type
                dev_eui = data.get('deveui', None)
                message_type = data['data_decoded'].get('message_type', None)
                print(f"DevEUI: {dev_eui}, Message Type: {message_type}")

                # Filter out unwanted message types
                if dev_eui and message_type:
                    sensor_type = message_type.lower()
                    if not any(unwanted in sensor_type for unwanted in
                               ["unknown", "supervisory message", "reset message", "downlink"]):
                        sensor_entry = {'DevEUI': dev_eui, 'sensor_type': sensor_type}
                        if sensor_entry not in sensor_list:
                            sensor_list.append(sensor_entry)
                            print(f"Sensor added: {sensor_entry}")
        message_buffer.append({
            'type': 'json',
            'topic': topic,
            'data': data
        })
    except json.JSONDecodeError:
        message_buffer.append({
            'type': 'text',
            'topic': topic,
            'data': message
        })
    except TypeError as e:
        print(f"TypeError: {e}")
        message_buffer.append({
            'type': 'error',
            'topic': topic,
            'data': f"Error processing message: {e}"
        })
    if len(message_buffer) > 150:
        message_buffer.pop(0)


"""
Following function is used to configure the temperature and humidity sensor downlink message.
"""


def encode_temperature_humidity_downlink(data):
    mode = int(data['mode'])
    reporting_interval = int(data['reporting_interval'])
    restoral_margin = int(data['restoral_margin'])
    lower_temp_threshold = int(data['lower_temp_threshold'])
    upper_temp_threshold = int(data['upper_temp_threshold'])
    lower_humidity_threshold = int(data['lower_humidity_threshold'])
    upper_humidity_threshold = int(data['upper_humidity_threshold'])

    downlink_message = [
        0x0D,  # Message type for Air Temperature and Humidity Sensor Event
        mode,
        reporting_interval,
        restoral_margin,
        lower_temp_threshold,
        upper_temp_threshold,
        lower_humidity_threshold,
        upper_humidity_threshold
    ]

    return base64.b64encode(bytes(downlink_message)).decode('utf-8')


"""
Following function is used to configure a sensor downlink message.
"""


def send_downlink(data, broker_ip):
    print(f"Using broker_ip in send_downlink: {broker_ip}")

    if not broker_ip:
        return {"error": "Invalid host."}, 500

    # Check if required keys are present
    if 'topic' not in data or 'sensor_type' not in data:
        return {"error": "Missing required keys: 'topic' or 'sensor_type'"}, 400

    topic = data['topic']
    sensor_type = data['sensor_type']
    downlink_message = []

    try:
        if sensor_type == 'water_sensor':
            enable_water_present = int(data['enableWaterPresent'])
            enable_water_not_present = int(data['enableWaterNotPresent'])
            threshold = int(data['threshold'])
            restoral = int(data['restoral'])
            enable_events = ((not enable_water_present) << 1) | (not enable_water_not_present)

            downlink_message = [
                0x08,  # Water sensor event
                enable_events,
                threshold,
                restoral,
                0x00, 0x00, 0x00, 0x00  # Padding with zeros
            ]

            print(f"Constructed downlink message: {downlink_message}")
        elif sensor_type == 'temp_humidity_sensor':
            mode = int(data['mode'], 16)
            reporting_interval = int(data['reportingInterval'])
            restoral_margin = int(data['restoralMargin'])
            lower_temp_threshold = int(data['lowerTempThreshold'])
            upper_temp_threshold = int(data['upperTempThreshold'])
            lower_humidity_threshold = int(data['lowerHumidityThreshold'])
            upper_humidity_threshold = int(data['upperHumidityThreshold'])
            downlink_message = [
                0x0D,  # Air Temperature and Humidity sensor configuration
                mode,
                reporting_interval,
                restoral_margin,
                lower_temp_threshold,
                upper_temp_threshold,
                lower_humidity_threshold,
                upper_humidity_threshold
            ]

        # Encode the message in base64
        downlink_message_base64 = base64.b64encode(bytes(downlink_message)).decode('utf-8')
        print(f"Base64 encoded downlink message: {downlink_message_base64}")

        payload = json.dumps({'data': downlink_message_base64})

        print(f"Payload: {payload}")

        publish.single(topic, payload, hostname=broker_ip)
        return {"message": "Downlink message sent successfully"}, 200
    except KeyError as e:
        print(f"KeyError: {e}")
        return {"error": f"Missing key in downlink data: {e}"}, 400
    except Exception as e:
        print(f"Error sending downlink: {e}")
        return {"error": str(e)}, 500
