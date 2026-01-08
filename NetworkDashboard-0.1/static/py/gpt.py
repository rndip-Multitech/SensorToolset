from dotenv import load_dotenv, find_dotenv
from openai import OpenAI
import os, json

"""
Load the OpenAI API key from the environment file and use it to call the OpenAI API
"""
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

api_key = os.environ.get('OPENAI_API_KEY')

if api_key:
    client = OpenAI(api_key=api_key)

"""
Import the OpenAI API key and use it to call the OpenAI API
Pass in MQTT JSON data and return a response from the OpenAI API
"""
def help_mqtt_json(json_data):
    if not api_key:
        return "OpenAI API key not found in the environment file."

    json_str = json.dumps(json_data, indent=2)
    completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system",
             "content": "You are an assistant on a MultiTech Systems utility website which is used for connecting to MultiTech Systems devices and configuring and sending uplink and downlink MQTT messages from these devices sensors to gateways."
                        "You are being asked with helping an end user decipher a JSON payload that was sent from a device to the MQTT broker. The user is asking for help with understanding the JSON payload and what it means."},
            {"role": "user", "content": f"This is the JSON data, explain what it means in detail: {json_str}"}
        ]
    )
    return completion.choices[0].message.content
