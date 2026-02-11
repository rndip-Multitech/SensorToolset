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

    // Derived booleans for status indicators / dashboards
    // These show up as status lights on the Sensors page.
    out.button_pressed = out.button_state === 'pressed';
    out.button_held = out.button_state === 'held';
    out.button_released = out.button_state === 'released';
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

  // --- Encoder helpers ---
  function hexByte(v) {
    v = Number(v);
    if (!Number.isFinite(v)) v = 0;
    v = Math.max(0, Math.min(255, v));
    return v.toString(16).padStart(2, '0');
  }
  function signedHexByte(v) {
    v = Number(v);
    if (!Number.isFinite(v)) v = 0;
    v = Math.max(-128, Math.min(127, v));
    if (v < 0) v = 256 + v;
    return v.toString(16).padStart(2, '0');
  }
  function periodicHex(mode, value) {
    var p = Number(value);
    if (!Number.isFinite(p) || p < 1 || p > 127) return '00';
    if (mode === 'disabled') return '00';
    if (mode === 'minutes') return (0x80 + p).toString(16).padStart(2, '0');
    if (mode === 'hours') return p.toString(16).padStart(2, '0');
    return '00';
  }
  function hexToBase64(hex) {
    var bytes = [];
    for (var i = 0; i < hex.length; i += 2) {
      bytes.push(parseInt(hex.substr(i, 2), 16));
    }
    return btoa(String.fromCharCode.apply(null, bytes));
  }

  // --- RadioBridge Encoders ---
  var radioBridgeEncoders = [
    // General Sensor Configuration (matches templates/GeneralConfig/script.js)
    {
      id: 'rb_general_config',
      name: 'General Sensor Configuration',
      defaultPort: 1,
      schema: [
        { key: 'disable_all_events', label: 'Disable All Events', type: 'select', options: [
          { value: 'no', label: 'No' }, { value: 'yes', label: 'Yes' }
        ]},
        { key: 'enable_adr', label: 'Enable ADR', type: 'select', options: [
          { value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }
        ]},
        { key: 'confirmed_messages', label: 'Use Confirmed Messages', type: 'select', options: [
          { value: 'no', label: 'No' }, { value: 'yes', label: 'Yes' }
        ]},
        { key: 'num_retries', label: 'Retries (0-7)', type: 'number', default: 0 },
        { key: 'time_type', label: 'Supervisory Interval Type', type: 'select', options: [
          { value: 'hours', label: 'Hours' }, { value: 'minutes', label: 'Minutes' }
        ]},
        { key: 'supervisory_interval', label: 'Supervisory Interval (1-127)', type: 'number', default: 24 },
        { key: 'sampling_period', label: 'Sampling Period', type: 'select', options: [
          { value: 'unchanged', label: 'Unchanged' },
          { value: 'milliseconds', label: 'Milliseconds' },
          { value: 'seconds', label: 'Seconds' },
          { value: 'minutes', label: 'Minutes' },
          { value: 'hours', label: 'Hours' }
        ]},
        { key: 'time_period', label: 'Time Period', type: 'number', default: 1 }
      ],
      encode: function (p) {
        function calcRadioHex(enableAdr, confirmed, retries) {
          var r = Math.max(0, Math.min(7, Number(retries) || 0));
          if (enableAdr && confirmed) {
            var valsAdrConfirmed = ['00', '04', '08', '0C', '10', '14', '18', '1C'];
            return valsAdrConfirmed[r];
          }
          if (!enableAdr && confirmed) {
            var valsNoAdrConfirmed = ['01', '05', '09', '0D', '11', '15', '19', '1D'];
            return valsNoAdrConfirmed[r];
          }
          if (enableAdr && !confirmed) return '06';
          return '07';
        }

        function calcSupervisoryHex(timeType, interval) {
          var i = Math.max(1, Math.min(127, Number(interval) || 1));
          if (timeType === 'minutes') return (0x80 + i).toString(16).toUpperCase().padStart(2, '0');
          return i.toString(16).toUpperCase().padStart(2, '0');
        }

        function calcSamplingHex(period, timePeriod) {
          var tp = Number(timePeriod) || 0;
          if (period === 'seconds') return (tp + 64).toString(16).toUpperCase().padStart(2, '0');
          if (period === 'minutes') return (tp + 128).toString(16).toUpperCase().padStart(2, '0');
          if (period === 'hours') return (tp + 192).toString(16).toUpperCase().padStart(2, '0');
          if (period === 'milliseconds') return Math.floor(tp / 250).toString(16).toUpperCase().padStart(2, '0');
          return '';
        }

        var disableEventsHex = p.disable_all_events === 'yes' ? '01' : '00';
        var adr = p.enable_adr !== 'no';
        var confirmed = p.confirmed_messages === 'yes';
        var radioHex = calcRadioHex(adr, confirmed, p.num_retries);
        var supervisoryHex = calcSupervisoryHex(p.time_type || 'hours', p.supervisory_interval);
        var samplingHex = calcSamplingHex(p.sampling_period || 'unchanged', p.time_period);
        var hex = '01' + disableEventsHex + radioHex + supervisoryHex + samplingHex + '00000000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },

    // Advanced Sensor Configuration (matches templates/AdvancedConfig/js/script.js)
    {
      id: 'rb_advanced_config',
      name: 'Advanced Sensor Configuration',
      defaultPort: 1,
      schema: [
        { key: 'link_quality_period', label: 'Link Quality Check Period', type: 'select', options: [
          { value: 'hours', label: 'Hours' }, { value: 'minutes', label: 'Minutes' }
        ]},
        { key: 'link_quality_value', label: 'Time Value', type: 'number', default: 24 }
      ],
      encode: function (p) {
        var v = Math.max(1, Math.min(127, Number(p.link_quality_value) || 1));
        var linkQualityValue = p.link_quality_period === 'minutes' ? (v + 128) : v;
        var linkQualityHex = linkQualityValue.toString(16).toUpperCase().padStart(2, '0');
        var hex = 'FC0001' + linkQualityHex + '00000000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },

    // Temperature Sensor
    {
      id: 'rb_temp_config',
      name: 'Temperature Sensor Config',
      defaultPort: 1,
      schema: [
        { key: 'sensor_type', label: 'Sensor Type', type: 'select', required: true, options: [
          { value: 'external', label: 'External Probe (RBS30x-TEMP-EXT)' },
          { value: 'internal', label: 'Internal (CMOS)' }
        ]},
        { key: 'mode', label: 'Reporting Mode', type: 'select', required: true, options: [
          { value: 'threshold', label: 'Threshold' },
          { value: 'roc', label: 'Report on Change' }
        ]},
        { key: 'periodic', label: 'Periodic Reporting', type: 'select', required: true, options: [
          { value: 'disabled', label: 'Disabled' },
          { value: 'minutes', label: 'Minutes' },
          { value: 'hours', label: 'Hours' }
        ]},
        { key: 'period_value', label: 'Period (1-127)', type: 'number', default: 60 },
        { key: 'threshold_lower', label: 'Lower Threshold (°C, -128 to 127)', type: 'number', default: 0 },
        { key: 'threshold_upper', label: 'Upper Threshold (°C, -128 to 127)', type: 'number', default: 30 },
        { key: 'roc_sensitivity', label: 'ROC Sensitivity (°C)', type: 'number', default: 5 },
        { key: 'roc_interval', label: 'ROC Interval', type: 'number', default: 0 },
        { key: 'restoral_margin', label: 'Restoral Margin (0-15)', type: 'number', default: 0 }
      ],
      encode: function (p) {
        var dnType = p.sensor_type === 'external' ? '09' : '19';
        var pHex = periodicHex(p.periodic, p.period_value);
        var mode = p.mode || 'threshold';
        var notif = mode === 'threshold' ? '00' : '01';
        var restoral = hexByte(Math.min(15, Math.max(0, Number(p.restoral_margin) || 0)));
        var byte5, byte6;
        if (mode === 'threshold') {
          byte5 = signedHexByte(p.threshold_lower);
          byte6 = signedHexByte(p.threshold_upper);
        } else {
          byte5 = hexByte(p.roc_sensitivity);
          byte6 = hexByte(p.roc_interval);
        }
        var hex = dnType + notif + pHex + restoral + byte5 + byte6 + '0000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // Movement Sensor (ABM)
    {
      id: 'rb_abm_config',
      name: 'Movement Sensor (ABM) Config',
      defaultPort: 1,
      schema: [
        { key: 'report_start', label: 'Report Movement Start', type: 'select', required: true, options: [
          { value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }
        ]},
        { key: 'report_stop', label: 'Report Movement Stop', type: 'select', required: true, options: [
          { value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }
        ]},
        { key: 'threshold', label: 'Acceleration Threshold (5-255)', type: 'number', default: 5 },
        { key: 'settling', label: 'Settling Window (0x05-0x3F)', type: 'number', default: 20 },
        { key: 'scaling', label: 'Scaling Factor', type: 'select', required: true, options: [
          { value: '00', label: '+/- 2g' },
          { value: '01', label: '+/- 4g' },
          { value: '02', label: '+/- 8g' },
          { value: '03', label: '+/- 16g' }
        ]}
      ],
      encode: function (p) {
        var movStart = p.report_start === 'yes';
        var movStop = p.report_stop === 'yes';
        var startStopHex = '03';
        if (movStart && movStop) startStopHex = '00';
        else if (movStart && !movStop) startStopHex = '02';
        else if (!movStart && movStop) startStopHex = '01';
        var actHex = hexByte(Math.max(5, Number(p.threshold) || 5));
        var swtHex = hexByte(Number(p.settling) || 20);
        var scalingHex = p.scaling || '00';
        var hex = '0E' + actHex + swtHex + scalingHex + startStopHex + '000000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // Door/Window Sensor
    {
      id: 'rb_door_window_config',
      name: 'Door/Window Sensor Config',
      defaultPort: 1,
      schema: [
        { key: 'periodic', label: 'Periodic Reporting', type: 'select', required: true, options: [
          { value: 'disabled', label: 'Disabled' },
          { value: 'minutes', label: 'Minutes' },
          { value: 'hours', label: 'Hours' }
        ]},
        { key: 'period_value', label: 'Period (1-127)', type: 'number', default: 60 },
        { key: 'debounce', label: 'Debounce Time (0-255, units of 10ms)', type: 'number', default: 10 }
      ],
      encode: function (p) {
        var pHex = periodicHex(p.periodic, p.period_value);
        var debounce = hexByte(Number(p.debounce) || 10);
        var hex = '03' + '00' + pHex + debounce + '00000000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // Contact Sensor
    {
      id: 'rb_contact_config',
      name: 'Contact Sensor Config',
      defaultPort: 1,
      schema: [
        { key: 'periodic', label: 'Periodic Reporting', type: 'select', required: true, options: [
          { value: 'disabled', label: 'Disabled' },
          { value: 'minutes', label: 'Minutes' },
          { value: 'hours', label: 'Hours' }
        ]},
        { key: 'period_value', label: 'Period (1-127)', type: 'number', default: 60 },
        { key: 'debounce', label: 'Debounce Time (0-255, units of 10ms)', type: 'number', default: 10 }
      ],
      encode: function (p) {
        var pHex = periodicHex(p.periodic, p.period_value);
        var debounce = hexByte(Number(p.debounce) || 10);
        var hex = '07' + '00' + pHex + debounce + '00000000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // Push Button Sensor
    {
      id: 'rb_push_button_config',
      name: 'Push Button Sensor Config',
      defaultPort: 1,
      schema: [
        { key: 'button_event', label: 'Button Event', type: 'select', required: true, options: [
          { value: '01', label: 'Pressed' },
          { value: '02', label: 'Released' },
          { value: '03', label: 'Pressed and Released' },
          { value: '04', label: 'Hold' },
          { value: '05', label: 'Pressed + Hold' },
          { value: '06', label: 'Released + Hold' },
          { value: '07', label: 'All Events' }
        ]},
        { key: 'hold_delay', label: 'Hold Delay (0-255, units of 0.5s)', type: 'number', default: 4 },
        { key: 'led_on_press', label: 'LED on Press', type: 'select', options: [
          { value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }
        ]},
        { key: 'led_on_release', label: 'LED on Release', type: 'select', options: [
          { value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }
        ]}
      ],
      encode: function (p) {
        var buttonEventHex = p.button_event || '07';
        var holdDelayHex = hexByte(Number(p.hold_delay) || 4);
        var ledFlags = 0;
        if (p.led_on_press === 'yes') ledFlags |= 0x01;
        if (p.led_on_release === 'yes') ledFlags |= 0x02;
        var ledFlagsHex = hexByte(ledFlags);
        var hex = '06' + buttonEventHex + holdDelayHex + ledFlagsHex + '00000000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // Tilt Sensor
    {
      id: 'rb_tilt_config',
      name: 'Tilt Sensor Config',
      defaultPort: 1,
      schema: [
        { key: 'enable_horiz', label: 'Enable Horizontal Tilt', type: 'select', options: [
          { value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }
        ]},
        { key: 'enable_vert', label: 'Enable Vertical Tilt', type: 'select', options: [
          { value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }
        ]},
        { key: 'angle_horiz', label: 'Horizontal Angle Threshold (0-90°)', type: 'number', default: 45 },
        { key: 'angle_vert', label: 'Vertical Angle Threshold (0-90°)', type: 'number', default: 45 },
        { key: 'hold_horiz', label: 'Horizontal Hold Time (0-255, units of 0.5s)', type: 'number', default: 10 },
        { key: 'hold_vert', label: 'Vertical Hold Time (0-255, units of 0.5s)', type: 'number', default: 10 },
        { key: 'roc_horiz', label: 'ROC Horizontal (0-90°)', type: 'number', default: 0 },
        { key: 'roc_vert', label: 'ROC Vertical (0-90°)', type: 'number', default: 0 }
      ],
      encode: function (p) {
        var enableTilts = 0;
        if (p.enable_horiz === 'yes') enableTilts |= 0x01;
        if (p.enable_vert === 'yes') enableTilts |= 0x02;
        var enableTiltsHex = hexByte(enableTilts);
        var angleHorizHex = hexByte(Math.min(90, Math.max(0, Number(p.angle_horiz) || 45)));
        var angleVertHex = hexByte(Math.min(90, Math.max(0, Number(p.angle_vert) || 45)));
        var holdHorizHex = hexByte(Number(p.hold_horiz) || 10);
        var holdVertHex = hexByte(Number(p.hold_vert) || 10);
        var rocHorizHex = hexByte(Math.min(90, Math.max(0, Number(p.roc_horiz) || 0)));
        var rocVertHex = hexByte(Math.min(90, Math.max(0, Number(p.roc_vert) || 0)));
        var hex = '0A' + '00' + enableTiltsHex + angleHorizHex + angleVertHex + holdVertHex + holdHorizHex + rocHorizHex + rocVertHex;
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // Water Sensor
    {
      id: 'rb_water_config',
      name: 'Water Sensor Config',
      defaultPort: 1,
      schema: [
        { key: 'report_water_present', label: 'Water Present Notification', type: 'select', options: [
          { value: 'yes', label: 'Enable' }, { value: 'no', label: 'Disable' }
        ]},
        { key: 'report_water_not_present', label: 'Water Not Present Notification', type: 'select', options: [
          { value: 'yes', label: 'Enable' }, { value: 'no', label: 'Disable' }
        ]},
        { key: 'threshold', label: 'Threshold (0-255)', type: 'number', default: 80 },
        { key: 'restoral_margin', label: 'Restoral Margin (0-255)', type: 'number', default: 0 }
      ],
      encode: function (p) {
        var wp = p.report_water_present !== 'no';
        var wnp = p.report_water_not_present !== 'no';
        var wpnpHex = '03';
        if (wp && wnp) wpnpHex = '00';
        else if (wp && !wnp) wpnpHex = '02';
        else if (!wp && wnp) wpnpHex = '01';
        var thresholdHex = hexByte(Number(p.threshold) || 80);
        var restoralHex = hexByte(Number(p.restoral_margin) || 0);
        var hex = '08' + wpnpHex + thresholdHex + restoralHex + '00000000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // Ultrasonic Level Sensor
    {
      id: 'rb_ultrasonic_config',
      name: 'Ultrasonic Level Sensor Config',
      defaultPort: 1,
      schema: [
        { key: 'reporting_type', label: 'Reporting Type', type: 'select', required: true, options: [
          { value: '00', label: 'Threshold' },
          { value: '01', label: 'Report on Change' }
        ]},
        { key: 'periodic', label: 'Periodic Reporting', type: 'select', required: true, options: [
          { value: 'disabled', label: 'Disabled' },
          { value: 'minutes', label: 'Minutes' },
          { value: 'hours', label: 'Hours' }
        ]},
        { key: 'period_value', label: 'Period (1-127)', type: 'number', default: 60 },
        { key: 'hold_time', label: 'Hold Time (0-255, units of 1s)', type: 'number', default: 5 },
        { key: 'value1', label: 'Threshold/ROC Value 1 (cm)', type: 'number', default: 50 },
        { key: 'value2', label: 'Threshold/ROC Value 2 (cm)', type: 'number', default: 200 }
      ],
      encode: function (p) {
        var reportingTypeHex = p.reporting_type || '00';
        var pHex = periodicHex(p.periodic, p.period_value);
        var holdTimeHex = hexByte(Number(p.hold_time) || 5);
        var val1 = Number(p.value1) || 50;
        var val2 = Number(p.value2) || 200;
        var value1Hex = ((val1 >> 8) & 0xFF).toString(16).padStart(2, '0') + (val1 & 0xFF).toString(16).padStart(2, '0');
        var value2Hex = ((val2 >> 8) & 0xFF).toString(16).padStart(2, '0') + (val2 & 0xFF).toString(16).padStart(2, '0');
        var hex = '10' + reportingTypeHex + pHex + holdTimeHex + value1Hex + value2Hex + '00';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // 4-20mA Sensor
    {
      id: 'rb_420ma_config',
      name: '4-20mA Current Loop Config',
      defaultPort: 1,
      schema: [
        { key: 'periodic', label: 'Periodic Reporting', type: 'select', required: true, options: [
          { value: 'disabled', label: 'Disabled' },
          { value: 'minutes', label: 'Minutes' },
          { value: 'hours', label: 'Hours' }
        ]},
        { key: 'period_value', label: 'Period (1-127)', type: 'number', default: 60 },
        { key: 'lower_threshold', label: 'Lower Threshold (mA, 0-20)', type: 'number', default: 4 },
        { key: 'upper_threshold', label: 'Upper Threshold (mA, 0-20)', type: 'number', default: 20 }
      ],
      encode: function (p) {
        var pHex = periodicHex(p.periodic, p.period_value);
        var lower = Math.round((Number(p.lower_threshold) || 4) * 10);
        var upper = Math.round((Number(p.upper_threshold) || 20) * 10);
        var lowerHex = hexByte(Math.min(255, Math.max(0, lower)));
        var upperHex = hexByte(Math.min(255, Math.max(0, upper)));
        var hex = '0A' + '00' + pHex + '00' + lowerHex + upperHex + '0000';
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    },
    // Air Temp & Humidity Sensor
    {
      id: 'rb_ath_config',
      name: 'Air Temp & Humidity Sensor Config',
      defaultPort: 1,
      schema: [
        { key: 'mode', label: 'Reporting Mode', type: 'select', required: true, options: [
          { value: 'threshold', label: 'Threshold' },
          { value: 'roc', label: 'Report on Change' }
        ]},
        { key: 'periodic', label: 'Periodic Reporting', type: 'select', required: true, options: [
          { value: 'disabled', label: 'Disabled' },
          { value: 'minutes', label: 'Minutes' },
          { value: 'hours', label: 'Hours' }
        ]},
        { key: 'period_value', label: 'Period (1-127)', type: 'number', default: 60 },
        { key: 'temp_lower', label: 'Temp Lower Threshold (°C)', type: 'number', default: 0 },
        { key: 'temp_upper', label: 'Temp Upper Threshold (°C)', type: 'number', default: 30 },
        { key: 'humidity_lower', label: 'Humidity Lower Threshold (%)', type: 'number', default: 20 },
        { key: 'humidity_upper', label: 'Humidity Upper Threshold (%)', type: 'number', default: 80 },
        { key: 'roc_temp', label: 'ROC Temp (°C)', type: 'number', default: 5 },
        { key: 'roc_humidity', label: 'ROC Humidity (%)', type: 'number', default: 10 }
      ],
      encode: function (p) {
        var mode = p.mode || 'threshold';
        var rocOrThreshHex = mode === 'threshold' ? '00' : '01';
        var pHex = periodicHex(p.periodic, p.period_value);
        var byte4, byte5, byte6, byte7;
        if (mode === 'threshold') {
          byte4 = signedHexByte(p.temp_lower);
          byte5 = signedHexByte(p.temp_upper);
          byte6 = hexByte(Number(p.humidity_lower) || 20);
          byte7 = hexByte(Number(p.humidity_upper) || 80);
        } else {
          byte4 = hexByte(Number(p.roc_temp) || 5);
          byte5 = hexByte(Number(p.roc_humidity) || 10);
          byte6 = '00';
          byte7 = '00';
        }
        var hex = '0D' + rocOrThreshHex + pHex + '00' + byte4 + byte5 + byte6 + byte7;
        return { port: 1, data_hex: hex, data_base64: hexToBase64(hex) };
      }
    }
  ];

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
    encoders: radioBridgeEncoders,
  });
})();

