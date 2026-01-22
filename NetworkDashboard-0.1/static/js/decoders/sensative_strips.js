// Sensative LoRa Strips - Complete Codec Plugin (decode + encode)
// Browser-safe version (no Node.js dependencies)

(function () {
  'use strict';
  if (!window.RBTDecoders) return;

  // ---- Helpers ----
  function getPort(message) {
    const d = message && message.data;
    if (!d) return 1; // Default to port 1 (direct uplink) if no data
    if (typeof d.port === 'number') return d.port;
    if (d.uplink_message && typeof d.uplink_message.f_port === 'number') return d.uplink_message.f_port;
    if (typeof d.fport === 'number') return d.fport;
    // MultiTech MQTT format doesn't include port, default to port 1 (direct uplink)
    // Port 1 is most common for Sensative Strips direct reports
    return 1;
  }

  function d2h(d, bytes) {
    const size = bytes * 2;
    let hex = Number(d).toString(16);
    if (hex.length > size) hex = hex.substring(hex.length - size);
    while (hex.length < size) hex = '0' + hex;
    return hex;
  }

  function h2d(hex) {
    return parseInt(hex, 16);
  }

  // ---- Decode helpers ----
  const EMPTY = { getsize: () => 0, decode: () => 0 };
  const UNSIGN1 = { getsize: () => 1, decode: (bytes, pos) => bytes[pos] };
  const UNS1FP2 = { getsize: (bytes, pos) => UNSIGN1.getsize(bytes, pos), decode: (bytes, pos) => UNSIGN1.decode(bytes, pos) / 2 };
  const UNSIGN2 = { getsize: () => 2, decode: (bytes, pos) => (bytes[pos++] << 8) + bytes[pos] };
  const SIGNED2 = {
    getsize: () => 2,
    decode: (bytes, pos) => ((bytes[pos] & 0x80 ? (0xFFFF << 16) : 0) | (bytes[pos++] << 8) | bytes[pos++]),
  };
  const SI2FP10 = { getsize: (bytes, pos) => SIGNED2.getsize(bytes, pos), decode: (bytes, pos) => SIGNED2.decode(bytes, pos) / 10 };
  const TMPALRM = { getsize: () => 1, decode: (bytes, pos) => ({ high: !!(bytes[pos] & 0x01), low: !!(bytes[pos] & 0x02) }) };
  const DIGITAL = { getsize: () => 1, decode: (bytes, pos) => !!bytes[pos] };
  const GIT_IDD = {
    getsize: () => 8,
    decode: (bytes, pos) => ({
      version: d2h(((bytes[pos++] << 24) >>> 0) + (bytes[pos++] << 16) + (bytes[pos++] << 8) + bytes[pos++], 4),
      idddata: d2h(((bytes[pos++] << 24) >>> 0) + (bytes[pos++] << 16) + (bytes[pos++] << 8) + bytes[pos++], 4),
    }),
  };
  const TEMPHUM = {
    getsize: (bytes, pos) => UNS1FP2.getsize(bytes, pos) + SI2FP10.getsize(bytes, pos + 1),
    decode: (bytes, pos) => ({
      humidity: { value: UNS1FP2.decode(bytes, pos), unit: '%' },
      temp: { value: SI2FP10.decode(bytes, pos + 1), unit: 'C' },
    }),
  };
  const TEMPDOR = {
    getsize: () => 3,
    decode: (bytes, pos) => ({
      door: { value: DIGITAL.decode(bytes, pos), unit: 'bool' },
      temp: { value: SI2FP10.decode(bytes, pos + 1), unit: 'C' },
    }),
  };

  const STRIPS_REPORTS = {
    CheckInConfirmed: { reportbit: 0, sensors: 0, coding: GIT_IDD, channel: 110, unit: '' },
    EmptyReport: { reportbit: -1, sensors: 0, coding: EMPTY, channel: 0, unit: '' },
    BatteryReport: { reportbit: 1, sensors: 0, coding: UNSIGN1, channel: 1, unit: '%' },
    TempReport: { reportbit: 2, sensors: 0, coding: SI2FP10, channel: 2, unit: 'C' },
    TempAlarm: { reportbit: 3, sensors: 0, coding: TMPALRM, channel: 3, unit: '' },
    AverageTempReport: { reportbit: 4, sensors: 0, coding: SI2FP10, channel: 4, unit: 'C' },
    AverageTempAlarm: { reportbit: 5, sensors: 0, coding: TMPALRM, channel: 5, unit: '' },
    HumidityReport: { reportbit: 6, sensors: 0, coding: UNS1FP2, channel: 6, unit: '%' },
    LuxReport: { reportbit: 7, sensors: 0, coding: UNSIGN2, channel: 7, unit: 'Lux' },
    LuxReport2: { reportbit: 8, sensors: 0, coding: UNSIGN2, channel: 8, unit: 'Lux' },
    DoorReport: { reportbit: 9, sensors: 0, coding: DIGITAL, channel: 9, unit: '' },
    DoorAlarm: { reportbit: 10, sensors: 0, coding: DIGITAL, channel: 10, unit: '' },
    TamperReport: { reportbit: 11, sensors: 0, coding: DIGITAL, channel: 11, unit: '' },
    TamperAlarm: { reportbit: 12, sensors: 0, coding: DIGITAL, channel: 12, unit: '' },
    FloodReport: { reportbit: 13, sensors: 0, coding: UNSIGN1, channel: 13, unit: '' },
    FloodAlarm: { reportbit: 14, sensors: 0, coding: DIGITAL, channel: 14, unit: '' },
    OilAlarm: { reportbit: 15, sensors: 0, coding: UNSIGN1, channel: 15, unit: '' },
    TempHumReport: { reportbit: 16, sensors: 0, coding: TEMPHUM, channel: 80, unit: '' },
    AvgTempHumReport: { reportbit: 17, sensors: 0, coding: TEMPHUM, channel: 81, unit: '' },
    TempDoorReport: { reportbit: 18, sensors: 0, coding: TEMPDOR, channel: 82, unit: '' },
  };

  const getReportFromByte = (channel) => {
    for (const report in STRIPS_REPORTS) {
      if (STRIPS_REPORTS[report].channel === channel) return report;
    }
    throw new Error('Unknown channel: ' + channel);
  };

  const decodeAndPackItem = (report, bytes, pos, hpos) => {
    const decodedItem = report.coding.decode(bytes, pos);
    const decoded = (typeof decodedItem === 'object') ? decodedItem : { value: decodedItem, unit: report.unit };
    if (hpos != null) decoded.historyPosition = hpos;
    return decoded;
  };

  const decodeDirectUplink = (bytes) => {
    if (bytes.length < 2) throw new Error('Too few bytes');
    let pos = 0;
    const hCount = (bytes[pos++] << 8) | bytes[pos++];
    const decoded = { historyStart: hCount };
    let historyPosition = hCount;

    while (pos < bytes.length) {
      let itemHistoryPosition = null;
      if (bytes[pos] & 0x80) itemHistoryPosition = historyPosition--;
      const reportName = getReportFromByte(bytes[pos++] & 0x7f);
      const report = STRIPS_REPORTS[reportName];
      const size = report.coding.getsize(bytes, pos);
      const nextpos = pos + size;
      if (nextpos > bytes.length) throw new Error('Incomplete data');
      decoded[reportName] = decodeAndPackItem(report, bytes, pos, itemHistoryPosition);
      pos = nextpos;
    }
    return [decoded];
  };

  const decodeHistoryUplink = (bytes) => {
    let pos = 0;
    const reports = [];
    const now = Date.now();
    if (bytes.length < 2) throw new Error('Too small history package');

    let sequence = (bytes[pos++] << 8) | bytes[pos++];

    while (pos < bytes.length - 5) {
      const timeOffsetMS = 1000 * (((bytes[pos++] << 24) >>> 0) | (bytes[pos++] << 16) | (bytes[pos++] << 8) | bytes[pos++]);
      const reportName = getReportFromByte(bytes[pos++] & 0x7f);
      const report = STRIPS_REPORTS[reportName];
      const size = report.coding.getsize(bytes, pos);
      const nextpos = pos + size;
      if (nextpos > bytes.length) throw new Error('Incomplete data');

      const decoded = { timestamp: now - timeOffsetMS };
      decoded[reportName] = decodeAndPackItem(report, bytes, pos, sequence++);
      reports.push(decoded);
      pos = nextpos;
    }
    if (pos !== bytes.length) throw new Error('Invalid history package size');
    return reports;
  };

  const decodeSettingsUplink = (bytes) => {
    let pos = 0;
    const result = [];
    if (bytes.length < 1) throw new Error('Too small settings package');

    const STATUS_CODES = ['OK', 'Bad setting', 'Bad payload length', 'Value not accepted', 'Unknown command'];

    while (pos < bytes.length) {
      const kind = bytes[pos++];
      if (kind === 3) {
        if (pos + 1 !== bytes.length) throw new Error('Bad status code message length');
        const status = bytes[pos++];
        if (status >= STATUS_CODES.length) throw new Error('Unknown status code: ' + status);
        result.push({ statusCode: { value: status, status: STATUS_CODES[status] } });
      } else {
        result.push({ kind, note: 'Settings decode kind not fully implemented in browser version' });
        break;
      }
    }
    return result;
  };

  const STRIPS_UPLINK_PORTS = {
    DIRECT_PORT: { port: 1, decode: decodeDirectUplink },
    HISTORY_PORT: { port: 2, decode: decodeHistoryUplink },
    SETTINGS_PORT: { port: 11, decode: decodeSettingsUplink },
  };

  const decodeLoraStripsUplink = (port, bytes) => {
    for (const kind in STRIPS_UPLINK_PORTS) {
      if (STRIPS_UPLINK_PORTS[kind].port === port) return STRIPS_UPLINK_PORTS[kind].decode(bytes);
    }
    throw new Error('No function for decoding uplinks on port ' + port);
  };

  // ---- Encode helpers ----
  const STRIPS_SETTINGS = {
    VERSION: { id: 0x01, name: 'Version' },
    BASE_POLL_INTERVAL: { id: 0x02, name: 'Base poll interval' },
    REPORTS_ENABLED: { id: 0x03, name: 'Reports enabled' },
    TEMP_HIGH_ALARM: { id: 0x09, name: 'Temp high alarm' },
    TEMP_LOW_ALARM: { id: 0x08, name: 'Temp low alarm' },
    HUMIDITY_TRESHOLD: { id: 0x12, name: 'Humidity treshold' },
    LUX_HIGH_LEVEL_1: { id: 0x14, name: 'Lux high level 1' },
    LUX_LOW_LEVEL_1: { id: 0x15, name: 'Lux low level 1' },
    FLOOD_ALARM_TRESHOLD: { id: 0x1c, name: 'Flood alarm treshold' },
    SENSOR_CONFIGURATION: { id: 0x32, name: 'Sensor configuration' },
  };

  const STRIPS_PROFILES = {
    DEFAULT: { id: 0x00, name: 'Default' },
    COMFORT_TEMP: { id: 0x01, name: 'Comfort Temp' },
    COMFORT_TEMP_LUX: { id: 0x02, name: 'Comfort Temp and Lux' },
    COMFORT_AVGTEMP: { id: 0x03, name: 'Comfort Average Temp' },
    GUARD_STD: { id: 0x04, name: 'Guard Standard' },
    DRIP_STD: { id: 0x05, name: 'Drip Standard' },
    PRESENCE_OFFICE: { id: 0x06, name: 'Presence Office' },
    PRESENCE_PUBLIC: { id: 0x07, name: 'Presence Public' },
    DISINFECT_OFFICE: { id: 0x08, name: 'Disinfect Office' },
    CLOSE_PROXIMITY_SLOW: { id: 0x09, name: 'Close Proximity Slow' },
  };

  function encodeU32(value) {
    return d2h(parseInt(value) || 0, 4);
  }

  function encodeSetSetting(params) {
    const settingName = params.setting;
    const value = params.value;
    if (!STRIPS_SETTINGS[settingName]) {
      throw new Error('Unknown setting: ' + settingName);
    }
    const settingId = STRIPS_SETTINGS[settingName].id;
    const valueNum = parseInt(value) || 0;
    return d2h(settingId, 1) + encodeU32(valueNum);
  }

  function encodeGetSetting(params) {
    const settingName = params.setting;
    if (!STRIPS_SETTINGS[settingName]) {
      throw new Error('Unknown setting: ' + settingName);
    }
    const settingId = STRIPS_SETTINGS[settingName].id;
    return d2h(settingId, 1);
  }

  function encodeSetProfile(params) {
    const profileName = params.profile;
    if (!STRIPS_PROFILES[profileName]) {
      throw new Error('Unknown profile: ' + profileName);
    }
    const profileId = STRIPS_PROFILES[profileName].id;
    return d2h(profileId, 1);
  }

  function encodeGetHistory(params) {
    const first = parseInt(params.first) || 0;
    const last = parseInt(params.last) || 0;
    return d2h(first, 2) + d2h(last, 2);
  }

  function encodeUnjoin(params) {
    const minutes = parseInt(params.minutes) || 0;
    return d2h(minutes, 2);
  }

  function hexToBase64(hex) {
    const bytes = new Uint8Array(hex.match(/.{1,2}/g).map(b => parseInt(b, 16)));
    return btoa(String.fromCharCode(...bytes));
  }

  // ---- Register Plugin ----
  window.RBTDecoders.registerDecoder({
    id: 'sensative_strips',
    name: 'Sensative LoRa Strips',
    priority: 150,
    canDecode: function (message) {
      // Try to detect Sensative Strips by payload structure
      // Since MultiTech MQTT doesn't include port, we'll default to port 1
      // and let manual selection always work
      const b64 = window.RBTDecoders.helpers.extractBase64Payload(message);
      if (!b64) return false;
      const bytes = window.RBTDecoders.helpers.base64ToBytes(b64);
      if (!bytes || bytes.length < 2) return false;
      // Sensative Strips direct uplinks start with history sequence (2 bytes)
      // History uplinks also start with sequence, settings uplinks are different
      // For now, allow if payload exists (manual selection will always work)
      return true;
    },
    decode: function (message) {
      try {
        let port = getPort(message);
        const b64 = window.RBTDecoders.helpers.extractBase64Payload(message);
        if (!b64) {
          return { eventType: 'sensative_strips', decoded: { error: 'No payload found', port } };
        }
        const bytes = window.RBTDecoders.helpers.base64ToBytes(b64);
        if (!bytes || bytes.length === 0) {
          return { eventType: 'sensative_strips', decoded: { error: 'Empty payload', port, payload_base64: b64 } };
        }
        
        // If port is 0 or unknown, try to detect from payload structure
        // Try port 1 (direct) first, then 2 (history), then 11 (settings)
        if (port === 0 || port === 1) {
          try {
            const decoded = decodeLoraStripsUplink(1, Array.from(bytes));
            return { eventType: 'sensative_strips', decoded: { port: 1, decoded } };
          } catch (e1) {
            // Try port 2 (history)
            try {
              const decoded = decodeLoraStripsUplink(2, Array.from(bytes));
              return { eventType: 'sensative_strips', decoded: { port: 2, decoded } };
            } catch (e2) {
              // Try port 11 (settings)
              try {
                const decoded = decodeLoraStripsUplink(11, Array.from(bytes));
                return { eventType: 'sensative_strips', decoded: { port: 11, decoded } };
              } catch (e3) {
                // All failed, return error with details
                return {
                  eventType: 'sensative_strips_error',
                  decoded: {
                    error: 'Failed to decode on ports 1, 2, or 11',
                    attempts: {
                      port1: String(e1 && e1.message ? e1.message : e1),
                      port2: String(e2 && e2.message ? e2.message : e2),
                      port11: String(e3 && e3.message ? e3.message : e3)
                    },
                    payload_base64: b64,
                    payload_hex: Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('')
                  }
                };
              }
            }
          }
        } else {
          // Port is known, use it directly
          const decoded = decodeLoraStripsUplink(port, Array.from(bytes));
          return { eventType: 'sensative_strips', decoded: { port, decoded } };
        }
      } catch (e) {
        // Return error info instead of throwing, so it shows in UI
        return { 
          eventType: 'sensative_strips_error', 
          decoded: { 
            error: String(e && e.message ? e.message : e),
            port: getPort(message),
            payload_base64: window.RBTDecoders.helpers.extractBase64Payload(message)
          } 
        };
      }
    },
    encoders: [
      {
        id: 'set_setting',
        name: 'Set Setting',
        defaultPort: 11,
        schema: [
          {
            key: 'setting',
            label: 'Setting',
            type: 'select',
            required: true,
            options: Object.keys(STRIPS_SETTINGS).map(k => ({ value: k, label: STRIPS_SETTINGS[k].name })),
          },
          {
            key: 'value',
            label: 'Value (decimal)',
            type: 'number',
            required: true,
            placeholder: '0',
          },
        ],
        encode: function (params) {
          const hex = '01' + encodeSetSetting(params);
          return { port: 11, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'get_setting',
        name: 'Get Setting',
        defaultPort: 11,
        schema: [
          {
            key: 'setting',
            label: 'Setting',
            type: 'select',
            required: true,
            options: Object.keys(STRIPS_SETTINGS).map(k => ({ value: k, label: STRIPS_SETTINGS[k].name })),
          },
        ],
        encode: function (params) {
          const hex = '02' + encodeGetSetting(params);
          return { port: 11, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'set_profile',
        name: 'Set Profile',
        defaultPort: 10,
        schema: [
          {
            key: 'profile',
            label: 'Profile',
            type: 'select',
            required: true,
            options: Object.keys(STRIPS_PROFILES).map(k => ({ value: k, label: STRIPS_PROFILES[k].name })),
          },
        ],
        encode: function (params) {
          const hex = '01' + encodeSetProfile(params);
          return { port: 10, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'get_history',
        name: 'Get History',
        defaultPort: 2,
        schema: [
          {
            key: 'first',
            label: 'First sequence number',
            type: 'number',
            required: true,
            default: 0,
          },
          {
            key: 'last',
            label: 'Last sequence number',
            type: 'number',
            required: true,
            default: 0,
          },
        ],
        encode: function (params) {
          const hex = '01' + encodeGetHistory(params);
          return { port: 2, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'unjoin',
        name: 'Unjoin',
        defaultPort: 10,
        schema: [
          {
            key: 'minutes',
            label: 'Minutes until unjoin',
            type: 'number',
            required: true,
            default: 0,
          },
        ],
        encode: function (params) {
          const hex = '08' + encodeUnjoin(params);
          return { port: 10, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
    ],
  });
})();
