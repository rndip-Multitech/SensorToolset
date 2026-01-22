// RadioBridge decoder (client-side JS)
// Decodes RadioBridge V3 payload bytes where:
// - byte0: protocol (upper nibble) + packet counter (lower nibble)
// - byte1: event code

(function () {
  'use strict';
  if (!window.RBTDecoders) return;

  function byteToSignedInt(n) {
    return n > 127 ? n - 256 : n;
  }

  const EVENT = {
    RESET: 0x00,
    SUPERVISORY: 0x01,
    TAMPER: 0x02,
    DOOR_WINDOW: 0x03,
    PUSH_BUTTON: 0x06,
    CONTACT: 0x07,
    WATER: 0x08,
    TEMPERATURE: 0x09,
    TILT: 0x0a,
    ATH: 0x0d,
    ABM: 0x0e,
    TILT_HP: 0x0f,
    ULTRASONIC: 0x10,
    SENSOR420MA: 0x11,
    THERMOCOUPLE: 0x13,
    VOLTMETER: 0x14,
    DEVICE_INFO: 0xfa,
    LINK_QUALITY: 0xfb,
    DOWNLINK_ACK: 0xff,
  };

  const KNOWN_EVENTS = new Set(Object.values(EVENT));

  function addHeaderFields(out, bytes) {
    if (!bytes || bytes.length < 1) return;
    out.packet_count = bytes[0] & 0x0f;
    out.protocol_version = (bytes[0] >> 4) & 0x0f;
  }

  function decodeReset(bytes) {
    const out = { event: 'reset' };
    const deviceTypeByte = bytes[2];
    const deviceTypeMap = {
      0x01: 'Door/Window Sensor',
      0x02: 'Door/Window High Security',
      0x03: 'Contact Sensor',
      0x04: 'No-Probe Temperature Sensor',
      0x05: 'External-Probe Temperature Sensor',
      0x06: 'Single Push Button',
      0x07: 'Dual Push Button',
      0x08: 'Acceleration-Based Movement Sensor',
      0x09: 'Tilt Sensor',
      0x0a: 'Water Sensor',
      0x0b: 'Tank Level Float Sensor',
      0x0c: 'Glass Break Sensor',
      0x0d: 'Ambient Light Sensor',
      0x0e: 'Air Temperature and Humidity Sensor',
      0x0f: 'High-Precision Tilt Sensor',
      0x10: 'Ultrasonic Level Sensor',
      0x11: '4-20mA Current Loop Sensor',
      0x12: 'Ext-Probe Air Temp and Humidity Sensor',
      0x13: 'Thermocouple Temperature Sensor',
      0x14: 'Voltage Sensor',
      0x15: 'Custom Sensor',
      0x16: 'GPS',
      0x17: 'Honeywell 5800 Bridge',
      0x18: 'Magnetometer',
      0x19: 'Vibration Sensor - Low Frequency',
      0x1a: 'Vibration Sensor - High Frequency',
    };
    out.device_type = deviceTypeMap[deviceTypeByte] || 'Device Undefined';

    // hardware version x.y
    if (bytes.length > 3) {
      out.hardware_version = `${(bytes[3] >> 4) & 0x0f}.${bytes[3] & 0x0f}`;
    }

    // firmware version old/new format using bytes[4] MSB
    if (bytes.length > 5) {
      const firmwareFormat = (bytes[4] >> 7) & 0x01;
      if (firmwareFormat === 0) {
        out.firmware_version = `${bytes[4]}.${bytes[5]}`;
      } else {
        const major = (bytes[4] >> 2) & 0x1f;
        const minor = (bytes[4] & 0x03) + ((bytes[5] >> 5) & 0x07);
        const patch = bytes[5] & 0x1f;
        out.firmware_version = `${major}.${minor}.${patch}`;
      }
    }

    return out;
  }

  function decodeSupervisory(bytes) {
    const out = { event: 'supervisory' };
    if (bytes.length > 4) {
      out.battery_level = parseFloat(`${(bytes[4] >> 4) & 0x0f}.${bytes[4] & 0x0f}`);
    }
    if (bytes.length > 10) {
      out.accumulation_count = (bytes[9] * 256) + bytes[10];
    }
    if (bytes.length > 2) {
      const flags = bytes[2];
      out.tamper_reset = ((flags >> 4) & 0x01) === 1;
      out.tamper_current = ((flags >> 3) & 0x01) === 1;
      out.downlink_error = ((flags >> 2) & 0x01) === 1;
      out.battery_low = ((flags >> 1) & 0x01) === 1;
      out.radio_error = (flags & 0x01) === 1;
    }
    return out;
  }

  function decodeTamper(bytes) {
    const out = { event: 'tamper' };
    const state = bytes.length > 2 ? bytes[2] : 0;
    out.tamper_state = state === 0 ? 'open' : 'closed';
    return out;
  }

  function decodeDoorWindow(bytes) {
    const out = { event: 'door_window' };
    const state = bytes.length > 2 ? bytes[2] : 0;
    out.state = state === 0 ? 'closed' : 'open';
    return out;
  }

  function decodePushButton(bytes) {
    const out = { event: 'push_button' };
    const buttonId = bytes.length > 2 ? bytes[2] : 0;
    const buttonMap = { 0x01: 'button_1', 0x02: 'button_2', 0x03: 'button_1', 0x12: 'button_1&2' };
    out.button_id = buttonMap[buttonId] || 'undefined';

    const buttonState = bytes.length > 3 ? bytes[3] : 0;
    const stateMap = { 0: 'pressed', 1: 'released', 2: 'held' };
    out.button_state = stateMap[buttonState] || 'undefined';
    return out;
  }

  function decodeContact(bytes) {
    const out = { event: 'contact' };
    const state = bytes.length > 2 ? bytes[2] : 0;
    out.state = state === 0 ? 'closed' : 'open';
    return out;
  }

  function decodeWater(bytes) {
    const out = { event: 'water' };
    const state = bytes.length > 2 ? bytes[2] : 0;
    out.state = state === 0 ? 'wet' : 'dry';
    out.relative_resistance = bytes.length > 3 ? bytes[3] : null;
    return out;
  }

  function decodeTemperature(bytes) {
    const out = { event: 'temperature' };
    const tempEvent = bytes.length > 2 ? bytes[2] : 0;
    const eventMap = {
      0: 'periodic_report',
      1: 'above_threshold',
      2: 'below_threshold',
      3: 'change_increase',
      4: 'change_decrease',
    };
    out.temperature_event = eventMap[tempEvent] || 'undefined';
    out.temperature_c = bytes.length > 3 ? byteToSignedInt(bytes[3]) : null;
    out.relative_temperature = bytes.length > 4 ? bytes[4] : null;
    return out;
  }

  function decodeTilt(bytes) {
    const out = { event: 'tilt' };
    const tiltEvent = bytes.length > 2 ? bytes[2] : 0;
    const eventMap = {
      0: 'transition_vertical',
      1: 'transition_horizontal',
      2: 'change_vertical',
      3: 'change_horizontal',
    };
    out.tilt_event = eventMap[tiltEvent] || 'undefined';
    out.tilt_angle = bytes.length > 3 ? bytes[3] : null;
    return out;
  }

  function decodeATH(bytes) {
    const out = { event: 'air_temperature_humidity' };
    const athEvent = bytes.length > 2 ? bytes[2] : 0;
    const eventMap = {
      0: 'periodic_report',
      1: 'temperature_above_threshold',
      2: 'temperature_below_threshold',
      3: 'temperature_change_increase',
      4: 'temperature_change_decrease',
      5: 'humidity_above_threshold',
      6: 'humidity_below_threshold',
      7: 'humidity_change_increase',
      8: 'humidity_change_decrease',
    };
    out.ath_event = eventMap[athEvent] || 'undefined';

    if (bytes.length > 6) {
      let sign = 1;
      let tempDigits = bytes[3];
      if (tempDigits > 127) {
        sign = -1;
        tempDigits = tempDigits - 128;
      }
      const tempFraction = (bytes[4] >> 4) / 10;
      out.temperature_c = sign * (tempDigits + tempFraction);
      out.humidity = bytes[5] + ((bytes[6] >> 4) / 10);
    }
    return out;
  }

  function decodeABM(bytes) {
    const out = { event: 'acceleration' };
    const abmEvent = bytes.length > 2 ? bytes[2] : 0;
    out.abm_event = abmEvent === 0 ? 'movement_start' : 'movement_stop';
    return out;
  }

  function decodeTiltHP(bytes) {
    const out = { event: 'hp_tilt' };
    const tiltEvent = bytes.length > 2 ? bytes[2] : 0;
    const eventMap = {
      0: 'periodic_report',
      1: 'toward_0_vertical',
      2: 'away_0_vertical',
      3: 'change_toward_0_vertical',
      4: 'change_away_0_vertical',
    };
    out.tilt_hp_event = eventMap[tiltEvent] || 'undefined';
    if (bytes.length > 5) {
      out.angle = bytes[3] + (bytes[4] / 10);
      out.temperature_c = byteToSignedInt(bytes[5]);
    }
    return out;
  }

  function decodeUltrasonic(bytes) {
    const out = { event: 'ultrasonic_level' };
    const uEvent = bytes.length > 2 ? bytes[2] : 0;
    const eventMap = {
      0: 'periodic_report',
      1: 'distance_above_threshold',
      2: 'distance_below_threshold',
      3: 'change_increase',
      4: 'change_decrease',
    };
    out.ultrasonic_event = eventMap[uEvent] || 'undefined';
    if (bytes.length > 4) out.distance = (bytes[3] * 256) + bytes[4];
    return out;
  }

  function decode420mA(bytes) {
    const out = { event: 'sensor420ma' };
    const aEvent = bytes.length > 2 ? bytes[2] : 0;
    const eventMap = {
      0: 'periodic_report',
      1: 'above_threshold',
      2: 'below_threshold',
      3: 'change_increase',
      4: 'change_decrease',
    };
    out.sensor420ma_event = eventMap[aEvent] || 'undefined';
    if (bytes.length > 4) out.current_milliamps = ((bytes[3] * 256) + bytes[4]) / 100;
    return out;
  }

  function decodeThermocouple(bytes) {
    const out = { event: 'thermocouple' };
    const tEvent = bytes.length > 2 ? bytes[2] : 0;
    const eventMap = {
      0: 'periodic_report',
      1: 'above_threshold',
      2: 'below_threshold',
      3: 'change_increase',
      4: 'change_decrease',
    };
    out.thermocouple_event = eventMap[tEvent] || 'undefined';
    if (bytes.length > 4) out.temperature_c = Math.trunc(((bytes[3] * 256) + bytes[4]) / 16);
    if (bytes.length > 5) {
      const faults = bytes[5];
      out.faults_byte = faults;
      out.faults = {
        cold_outside_range: ((faults >> 7) & 0x01) === 1,
        hot_outside_range: ((faults >> 6) & 0x01) === 1,
        cold_above_thresh: ((faults >> 5) & 0x01) === 1,
        cold_below_thresh: ((faults >> 4) & 0x01) === 1,
        tc_too_high: ((faults >> 3) & 0x01) === 1,
        tc_too_low: ((faults >> 2) & 0x01) === 1,
        voltage_outside_range: ((faults >> 1) & 0x01) === 1,
        open_circuit: (faults & 0x01) === 1,
      };
    }
    return out;
  }

  function decodeVoltmeter(bytes) {
    const out = { event: 'voltmeter' };
    const vEvent = bytes.length > 2 ? bytes[2] : 0;
    const eventMap = {
      0: 'periodic_report',
      1: 'above_threshold',
      2: 'below_threshold',
      3: 'change_increase',
      4: 'change_decrease',
    };
    out.voltmeter_event = eventMap[vEvent] || 'undefined';
    if (bytes.length > 4) out.volts = ((bytes[3] * 256) + bytes[4]) / 100;
    return out;
  }

  function decodeDeviceInfo(bytes) {
    const out = { event: 'device_info' };
    const b = bytes.length > 2 ? bytes[2] : 0;
    const index = (b >> 4) & 0x0f;
    const total = b & 0x0f;
    out.message = `${index} of ${total}`;
    if (bytes.length > 10) {
      const slice = bytes.slice(3, 10);
      out.downlinkBytes = Array.from(slice).map((x) => x.toString(16).padStart(2, '0').toUpperCase()).join(' ');
    }
    return out;
  }

  function decodeLinkQuality(bytes) {
    const out = { event: 'link_quality' };
    if (bytes.length > 4) {
      out.sub_band = bytes[2];
      out.rssi = bytes[3];
      out.snr = bytes[4];
    }
    return out;
  }

  function decodeDownlinkAck(bytes) {
    const out = { event: 'downlink_ack' };
    const dl = bytes.length > 2 ? bytes[2] : 0;
    out.downlink_ack_event = dl === 1 ? 'message_invalid' : 'message_valid';
    return out;
  }

  function decodeRadioBridgeBytes(bytes) {
    const out = {};
    addHeaderFields(out, bytes);
    if (!bytes || bytes.length < 2) {
      out.event = 'invalid';
      out.error = 'Payload too short';
      return out;
    }
    const event = bytes[1];
    let decoded;
    switch (event) {
      case EVENT.RESET:
        decoded = decodeReset(bytes);
        break;
      case EVENT.SUPERVISORY:
        decoded = decodeSupervisory(bytes);
        break;
      case EVENT.TAMPER:
        decoded = decodeTamper(bytes);
        break;
      case EVENT.DOOR_WINDOW:
        decoded = decodeDoorWindow(bytes);
        break;
      case EVENT.PUSH_BUTTON:
        decoded = decodePushButton(bytes);
        break;
      case EVENT.CONTACT:
        decoded = decodeContact(bytes);
        break;
      case EVENT.WATER:
        decoded = decodeWater(bytes);
        break;
      case EVENT.TEMPERATURE:
        decoded = decodeTemperature(bytes);
        break;
      case EVENT.TILT:
        decoded = decodeTilt(bytes);
        break;
      case EVENT.ATH:
        decoded = decodeATH(bytes);
        break;
      case EVENT.ABM:
        decoded = decodeABM(bytes);
        break;
      case EVENT.TILT_HP:
        decoded = decodeTiltHP(bytes);
        break;
      case EVENT.ULTRASONIC:
        decoded = decodeUltrasonic(bytes);
        break;
      case EVENT.SENSOR420MA:
        decoded = decode420mA(bytes);
        break;
      case EVENT.THERMOCOUPLE:
        decoded = decodeThermocouple(bytes);
        break;
      case EVENT.VOLTMETER:
        decoded = decodeVoltmeter(bytes);
        break;
      case EVENT.DEVICE_INFO:
        decoded = decodeDeviceInfo(bytes);
        break;
      case EVENT.LINK_QUALITY:
        decoded = decodeLinkQuality(bytes);
        break;
      case EVENT.DOWNLINK_ACK:
        decoded = decodeDownlinkAck(bytes);
        break;
      default:
        decoded = { event: 'unknown', event_code: event };
    }
    return Object.assign(out, decoded);
  }

  window.RBTDecoders.registerDecoder({
    id: 'radiobridge_js',
    name: 'RadioBridge (JS)',
    priority: 100,
    canDecode: function (message) {
      const b64 = window.RBTDecoders.helpers.extractBase64Payload(message);
      const bytes = window.RBTDecoders.helpers.base64ToBytes(b64);
      if (!bytes || bytes.length < 2) return false;
      return KNOWN_EVENTS.has(bytes[1]);
    },
    decode: function (message) {
      const b64 = window.RBTDecoders.helpers.extractBase64Payload(message);
      const bytes = window.RBTDecoders.helpers.base64ToBytes(b64);
      const decoded = decodeRadioBridgeBytes(bytes);
      decoded.payload_hex = window.RBTDecoders.helpers.bytesToHex(bytes || []);
      decoded.payload_len = bytes ? bytes.length : 0;
      return window.RBTDecoders.normalizeDecodedOutput(decoded);
    },
  });
})();

