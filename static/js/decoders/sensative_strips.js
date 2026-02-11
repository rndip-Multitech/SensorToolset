// Sensative LoRa Strips - Codec (decode + encode)
// Browser-safe, aligned with https://github.com/Sensative/strips-lora-translator-open-source (strips-translate.js)

(function () {
  'use strict';
  if (!window.RBTDecoders) return;

  function getPort(message) {
    const d = message && message.data;
    if (!d) return 1;
    if (typeof d.port === 'number') return d.port;
    if (d.uplink_message && typeof d.uplink_message.f_port === 'number') return d.uplink_message.f_port;
    if (typeof d.fport === 'number') return d.fport;
    return 1;
  }

  function d2h(d, bytes) {
    const size = bytes * 2;
    let hex = Number(d).toString(16);
    if (hex.length > size) hex = hex.substring(hex.length - size);
    while (hex.length < size) hex = '0' + hex;
    return hex;
  }

  const decodeU32dec = (n) => String(n);
  const decodeU32hex = (n) => '0x' + n.toString(16);
  const encodeU32hex = (value) => {
    const n = parseInt(String(value).replace(/^0x/i, ''), 16);
    return d2h(Number.isNaN(n) ? 0 : n, 4);
  };
  const encodeU32 = (value) => d2h(Number(value) || 0, 4);

  // ---- Decode helpers (match original) ----
  const EMPTY = { getsize: () => 0, decode: () => 0 };
  const UNSIGN1 = { getsize: () => 1, decode: (bytes, pos) => bytes[pos] };
  const UNS1FP2 = { getsize: (b, p) => UNSIGN1.getsize(b, p), decode: (bytes, pos) => UNSIGN1.decode(bytes, pos) / 2 };
  const UNSIGN2 = { getsize: () => 2, decode: (bytes, pos) => (bytes[pos++] << 8) + bytes[pos] };
  const SIGNED2 = {
    getsize: () => 2,
    decode: (bytes, pos) => ((bytes[pos] & 0x80 ? 0xFFFF << 16 : 0) | (bytes[pos++] << 8) | bytes[pos++]),
  };
  const SI2FP10 = { getsize: (b, p) => SIGNED2.getsize(b, p), decode: (bytes, pos) => SIGNED2.decode(bytes, pos) / 10 };
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
    getsize: (b, p) => UNS1FP2.getsize(b, p) + SI2FP10.getsize(b, p + 1),
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

  const STRIPS_SENSOR = {
    BUTTON: 1 << 1,
    BATTERY: 1 << 2,
    TEMP: 1 << 3,
    HUMID: 1 << 4,
    LUX: 1 << 5,
    DOOR: 1 << 6,
    TAMPER: 1 << 7,
    CAP: 1 << 8,
    PROX: 1 << 9,
  };

  const STRIPS_REPORTS = {
    CheckInConfirmed: { reportbit: 0, sensors: STRIPS_SENSOR.BUTTON, coding: GIT_IDD, channel: 110, unit: '' },
    EmptyReport: { reportbit: -1, sensors: STRIPS_SENSOR.BUTTON, coding: EMPTY, channel: 0, unit: '' },
    BatteryReport: { reportbit: 1, sensors: STRIPS_SENSOR.BATTERY, coding: UNSIGN1, channel: 1, unit: '%' },
    TempReport: { reportbit: 2, sensors: STRIPS_SENSOR.TEMP, coding: SI2FP10, channel: 2, unit: 'C' },
    TempAlarm: { reportbit: 3, sensors: STRIPS_SENSOR.TEMP, coding: TMPALRM, channel: 3, unit: '' },
    AverageTempReport: { reportbit: 4, sensors: STRIPS_SENSOR.TEMP, coding: SI2FP10, channel: 4, unit: 'C' },
    AverageTempAlarm: { reportbit: 5, sensors: STRIPS_SENSOR.TEMP, coding: TMPALRM, channel: 5, unit: '' },
    HumidityReport: { reportbit: 6, sensors: STRIPS_SENSOR.HUMID, coding: UNS1FP2, channel: 6, unit: '%' },
    LuxReport: { reportbit: 7, sensors: STRIPS_SENSOR.LUX, coding: UNSIGN2, channel: 7, unit: 'Lux' },
    LuxReport2: { reportbit: 8, sensors: STRIPS_SENSOR.LUX, coding: UNSIGN2, channel: 8, unit: 'Lux' },
    DoorReport: { reportbit: 9, sensors: STRIPS_SENSOR.DOOR, coding: DIGITAL, channel: 9, unit: '' },
    DoorAlarm: { reportbit: 10, sensors: STRIPS_SENSOR.DOOR, coding: DIGITAL, channel: 10, unit: '' },
    TamperReport: { reportbit: 11, sensors: STRIPS_SENSOR.TAMPER, coding: DIGITAL, channel: 11, unit: '' },
    TamperAlarm: { reportbit: 12, sensors: STRIPS_SENSOR.TAMPER, coding: DIGITAL, channel: 12, unit: '' },
    FloodReport: { reportbit: 13, sensors: STRIPS_SENSOR.CAP, coding: UNSIGN1, channel: 13, unit: '' },
    FloodAlarm: { reportbit: 14, sensors: STRIPS_SENSOR.CAP, coding: DIGITAL, channel: 14, unit: '' },
    OilAlarm: { reportbit: 15, sensors: STRIPS_SENSOR.CAP, coding: UNSIGN1, channel: 15, unit: '' },
    TempHumReport: { reportbit: 16, sensors: STRIPS_SENSOR.TEMP | STRIPS_SENSOR.HUMID, coding: TEMPHUM, channel: 80, unit: '' },
    AvgTempHumReport: { reportbit: 17, sensors: STRIPS_SENSOR.TEMP | STRIPS_SENSOR.HUMID, coding: TEMPHUM, channel: 81, unit: '' },
    TempDoorReport: { reportbit: 18, sensors: STRIPS_SENSOR.TEMP | STRIPS_SENSOR.DOOR, coding: TEMPDOR, channel: 82, unit: '' },
    CapacitanceFloodReport: { reportbit: 19, sensors: STRIPS_SENSOR.CAP, coding: UNSIGN2, channel: 112, unit: '' },
    CapacitancePadReport: { reportbit: 20, sensors: STRIPS_SENSOR.CAP, coding: UNSIGN2, channel: 113, unit: '' },
    CapacitanceEndReport: { reportbit: 21, sensors: STRIPS_SENSOR.CAP, coding: UNSIGN2, channel: 114, unit: '' },
    UserSwitchAlarm: { reportbit: 22, sensors: STRIPS_SENSOR.TAMPER, coding: DIGITAL, channel: 16, unit: '' },
    DoorCountReport: { reportbit: 23, sensors: STRIPS_SENSOR.DOOR, coding: UNSIGN2, channel: 17, unit: '' },
    PresenceReport: { reportbit: 24, sensors: STRIPS_SENSOR.PROX, coding: DIGITAL, channel: 18, unit: '' },
    IRProximityReport: { reportbit: 25, sensors: STRIPS_SENSOR.PROX, coding: UNSIGN2, channel: 19, unit: '' },
    IRCloseProximityReport: { reportbit: 26, sensors: STRIPS_SENSOR.PROX, coding: UNSIGN2, channel: 20, unit: '' },
    CloseProximityAlarm: { reportbit: 27, sensors: STRIPS_SENSOR.PROX, coding: DIGITAL, channel: 21, unit: '' },
    DisinfectAlarm: { reportbit: 28, sensors: STRIPS_SENSOR.PROX, coding: UNSIGN1, channel: 22, unit: '' },
  };

  const decodeReports = (n) => {
    let result = '';
    for (const report in STRIPS_REPORTS) {
      const rb = STRIPS_REPORTS[report].reportbit;
      if (rb >= 0 && (n & (1 << rb))) {
        if (result) result += '|';
        result += report;
      }
    }
    return result;
  };

  const encodeReports = (str) => {
    const list = String(str || '').split('|');
    let res = 0;
    for (let i = 0; i < list.length; i++) {
      const item = list[i].trim();
      if (!item) continue;
      if (!STRIPS_REPORTS.hasOwnProperty(item)) throw new Error('Invalid report id: ' + item);
      const rb = STRIPS_REPORTS[item].reportbit;
      if (rb >= 0) res |= 1 << rb;
    }
    return d2h(res, 4);
  };

  const SENSOR_CONFIG_BITS = { INVERT_DOOR: 1 << 0, HIGH_POWER_PROXIMITY: 1 << 1 };
  const decodeConfig = (n) => {
    let r = '';
    for (const bitname in SENSOR_CONFIG_BITS) {
      if (n & SENSOR_CONFIG_BITS[bitname]) {
        if (r) r += '|';
        r += bitname;
      }
    }
    return r;
  };
  const encodeConfig = (str) => {
    const list = String(str || '').split('|');
    let res = 0;
    for (let i = 0; i < list.length; i++) {
      const item = list[i].trim();
      for (const bitname in SENSOR_CONFIG_BITS) {
        if (item === bitname) res |= SENSOR_CONFIG_BITS[bitname];
      }
    }
    return d2h(res, 4);
  };

  const STRIPS_SETTINGS = {
    NONE: { id: 0x00, unit: 'none', decode: decodeU32hex, encode: encodeU32hex, name: 'None' },
    VERSION: { id: 0x01, unit: 'version', decode: decodeU32hex, encode: encodeU32hex, name: 'Version' },
    BASE_POLL_INTERVAL: { id: 0x02, unit: 'ms', decode: decodeU32dec, encode: encodeU32, name: 'Base poll interval' },
    REPORTS_ENABLED: { id: 0x03, unit: 'reports', decode: decodeReports, encode: encodeReports, name: 'Reports enabled' },
    TEMP_POLL_INTERVAL: { id: 0x04, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Temp poll interval' },
    TEMP_SEND_IMMEDIATELY_TRESHOLD: { id: 0x05, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Temp send immediately treshold' },
    TEMP_SEND_THROTTLED_TRESHOLD: { id: 0x06, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Temp send throttled treshold' },
    TEMP_SEND_THROTTLED_TIME: { id: 0x07, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Temp send throttled time' },
    TEMP_LOW_ALARM: { id: 0x08, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Temp low alarm' },
    TEMP_HIGH_ALARM: { id: 0x09, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Temp high alarm' },
    TEMP_ALARM_HYSTERESIS: { id: 0x0A, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Temp alarm hysteresis' },
    AVGTEMP_AVERAGE_TIME: { id: 0x0B, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Average temp average time' },
    AVGTEMP_MIN_TEMP: { id: 0x0C, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Average temp min temp' },
    AVGTEMP_SEND_IMMEDIATELY_TRESHOLD: { id: 0x0D, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Avg temp send immediately treshold' },
    AVGTEMP_LOW_ALARM: { id: 0x0E, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Average temp low alarm' },
    AVGTEMP_HIGH_ALARM: { id: 0x0F, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Average temp high alarm' },
    AVGTEMP_ALARM_HYSTERESIS: { id: 0x10, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Average temp hysteresis' },
    HUMIDITY_POLL_INTERVAL: { id: 0x11, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Humidity poll interval' },
    HUMIDITY_TRESHOLD: { id: 0x12, unit: '%', decode: decodeU32dec, encode: encodeU32, name: 'Humidity treshold' },
    LUX_POLL_INTERVAL: { id: 0x13, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Lux poll interval' },
    LUX_HIGH_LEVEL_1: { id: 0x14, unit: 'Lux', decode: decodeU32dec, encode: encodeU32, name: 'Lux high level 1' },
    LUX_LOW_LEVEL_1: { id: 0x15, unit: 'Lux', decode: decodeU32dec, encode: encodeU32, name: 'Lux low level 1' },
    LUX_HIGH_LEVEL_2: { id: 0x16, unit: 'Lux', decode: decodeU32dec, encode: encodeU32, name: 'Lux high level 2' },
    LUX_LOW_LEVEL_2: { id: 0x17, unit: 'Lux', decode: decodeU32dec, encode: encodeU32, name: 'Lux low level 2' },
    FLOOD_POLL_INTERVAL: { id: 0x18, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Flood poll interval' },
    FLOOD_CAPACITANCE_MIN: { id: 0x19, unit: 'capacitance', decode: decodeU32dec, encode: encodeU32, name: 'Flood capacitance min' },
    FLOOD_CAPACITANCE_MAX: { id: 0x1A, unit: 'capacitance', decode: decodeU32dec, encode: encodeU32, name: 'Flood capacitance max' },
    FLOOD_REPORT_INTERVAL: { id: 0x1B, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Flood report interval' },
    FLOOD_ALARM_TRESHOLD: { id: 0x1C, unit: '%', decode: decodeU32dec, encode: encodeU32, name: 'Flood alarm treshold' },
    FLOOD_ALARM_HYSTERESIS: { id: 0x1D, unit: '%', decode: decodeU32dec, encode: encodeU32, name: 'Flood alarm hysteresis' },
    SETTINGS_FOIL_TRESHOLD: { id: 0x1E, unit: 'capacitance', decode: decodeU32dec, encode: encodeU32, name: 'Foil treshold' },
    CAPACITANCE_FLOOD_REPORT_INTERVAL: { id: 0x1F, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Cap flood report interval' },
    CAPACITANCE_PAD_REPORT_INTERVAL: { id: 0x20, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Cap pad report interval' },
    CAPACITANCE_END_REPORT_INTERVAL: { id: 0x21, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Cap end report interval' },
    SENSORS_COMBINED_1: { id: 0x22, unit: 'reports', decode: decodeReports, encode: encodeReports, name: 'Combined reports 1' },
    SENSORS_COMBINED_2: { id: 0x23, unit: 'reports', decode: decodeReports, encode: encodeReports, name: 'Combined reports 2' },
    SENSORS_COMBINED_3: { id: 0x24, unit: 'reports', decode: decodeReports, encode: encodeReports, name: 'Combined reports 3' },
    HISTORY_REPORTS: { id: 0x25, unit: 'reports', decode: decodeReports, encode: encodeReports, name: 'History reports' },
    DEMO_TRYJOIN_INTERVAL: { id: 0x26, unit: 'min', decode: decodeU32dec, encode: encodeU32, name: 'Try join interval' },
    LUX_PLASTIC_COMP: { id: 0x27, unit: '%', decode: decodeU32dec, encode: encodeU32, name: 'Lux plastic comp' },
    LORA_DATA_RATE: { id: 0x28, unit: 'datarate', decode: decodeU32dec, encode: encodeU32, name: 'Lora data rate' },
    LED_LEVEL: { id: 0x29, unit: 'ledlevel', decode: decodeU32dec, encode: encodeU32, name: 'Led level' },
    LINK_CHECK_INTERVAL: { id: 0x2A, unit: 'unknown', decode: decodeU32dec, encode: encodeU32, name: 'Link check interval' },
    RESEND_RESET_TIME: { id: 0x2B, unit: 'unknown', decode: decodeU32dec, encode: encodeU32, name: 'Resend reset time' },
    LUX_LOW_CUTOFF: { id: 0x2C, unit: 'lux', decode: decodeU32dec, encode: encodeU32, name: 'Lux low cutoff' },
    DOOR_COUNT_REPORT_INTERVAL: { id: 0x2D, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Door count interval' },
    IR_PROXIMITY_REPORT_INTERVAL: { id: 0x2E, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'IR Proximity report interval' },
    PRESENCE_POLL_INTERVAL: { id: 0x2F, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Presence poll interval' },
    PRESENCE_TRESHOLD: { id: 0x30, unit: 'reflection', decode: decodeU32dec, encode: encodeU32, name: 'Presence treshold' },
    PRESENCE_TIMEOUT: { id: 0x31, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Presence timeout' },
    SENSOR_CONFIGURATION: { id: 0x32, unit: 'config', decode: decodeConfig, encode: encodeConfig, name: 'Sensor configuration' },
    FACTORY_TEMPERATURE_CALIBRATION: { id: 0x33, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'Factory Internal Temp Calibration' },
    USER_TEMPERATURE_CALIBRATION: { id: 0x34, unit: 'mC', decode: decodeU32dec, encode: encodeU32, name: 'User Temp Calibration' },
    LUX_FILTERFACTOR: { id: 0x35, unit: 'count', decode: decodeU32dec, encode: encodeU32, name: 'Lux Filter Factor' },
    LUX_VERIFICATION_POLL_INTERVAL: { id: 0x36, unit: 's', decode: decodeU32dec, encode: encodeU32, name: 'Lux Verification Poll Interval' },
    OIL_FILTERFACTOR: { id: 0x37, unit: 'count', decode: decodeU32dec, encode: encodeU32, name: 'Oil Filter Factor' },
    OIL_HYSTERESIS: { id: 0x38, unit: 'capacitance', decode: decodeU32dec, encode: encodeU32, name: 'Oil Hysteresis' },
    CONFIRMED_REPORTS_MASK: { id: 0x39, unit: 'reports', decode: decodeReports, encode: encodeReports, name: 'Confirmed reports' },
    IR_PROXIMITY_COUNT: { id: 0x3a, unit: 'count', decode: decodeU32dec, encode: encodeU32, name: 'Close Proximity Confirm Count' },
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
    ALL_CAP_SENSORS_RAW: { id: 0xF0, name: 'All cap sensors raw' },
  };

  function getSettingById(id) {
    for (const setting in STRIPS_SETTINGS) {
      if (STRIPS_SETTINGS[setting].id === id) return setting;
    }
    return null;
  }

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

  const STATUS_CODES = ['OK', 'Bad setting', 'Bad payload length', 'Value not accepted', 'Unknown command'];

  const decodeSettingsUplink = (bytes) => {
    let pos = 0;
    const result = [];
    if (bytes.length < 1) throw new Error('Too small settings package');
    while (pos < bytes.length) {
      const kind = bytes[pos++];
      if (kind === 2) {
        if (pos + 5 > bytes.length) throw new Error('Incomplete settings data');
        const id = bytes[pos++];
        const setting = getSettingById(id);
        if (!setting) throw new Error('Unknown setting id ' + id);
        const raw = ((bytes[pos++] << 24) >>> 0) | (bytes[pos++] << 16) | (bytes[pos++] << 8) | bytes[pos++];
        const decoded = {};
        decoded[setting] = { id, name: STRIPS_SETTINGS[setting].name, unit: STRIPS_SETTINGS[setting].unit, value: STRIPS_SETTINGS[setting].decode(raw) };
        result.push(decoded);
      } else if (kind === 3) {
        if (pos + 1 !== bytes.length) throw new Error('Bad status code message length');
        const status = bytes[pos++];
        if (status >= STATUS_CODES.length) throw new Error('Unknown status code: ' + status);
        result.push({ statusCode: { value: status, status: STATUS_CODES[status] } });
      } else {
        throw new Error('Unknown settings uplink format: ' + kind);
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
    for (const k in STRIPS_UPLINK_PORTS) {
      if (STRIPS_UPLINK_PORTS[k].port === port) return STRIPS_UPLINK_PORTS[k].decode(bytes);
    }
    throw new Error('No function for decoding uplinks on port ' + port);
  };

  // ---- Encode (downlink) ----
  function encodeSetSettingObj(settingName, value) {
    const s = STRIPS_SETTINGS[settingName];
    if (!s) throw new Error('Unknown setting: ' + settingName);
    return d2h(s.id, 1) + s.encode(value);
  }

  function encodeGetSettingObj(settingName) {
    const s = STRIPS_SETTINGS[settingName];
    if (!s) throw new Error('Unknown setting: ' + settingName);
    return d2h(s.id, 1);
  }

  function encodeSetProfileObj(profileId) {
    const p = STRIPS_PROFILES[profileId];
    if (!p) throw new Error('Unknown profile: ' + profileId);
    return d2h(p.id, 1);
  }

  function encodeGetHistoryObj(first, last) {
    return d2h(Number(first) || 0, 2) + d2h(Number(last) || 0, 2);
  }

  function encodeCmdUnjoinObj(minutes) {
    return d2h(Number(minutes) || 0, 2);
  }

  function encodeEndCompObj() {
    return '';
  }

  function hexToBase64(hex) {
    const m = (hex || '').replace(/\s/g, '').match(/.{1,2}/g);
    if (!m || m.length === 0) return '';
    const bytes = new Uint8Array(m.map(b => parseInt(b, 16)));
    return btoa(String.fromCharCode.apply(null, bytes));
  }

  const SETTINGS_KEYS = Object.keys(STRIPS_SETTINGS).filter(k => k !== 'NONE');
  const PROFILE_KEYS = Object.keys(STRIPS_PROFILES);

  window.RBTDecoders.registerDecoder({
    id: 'sensative_strips',
    name: 'Sensative LoRa Strips',
    priority: 150,
    canDecode: function (message) {
      const b64 = window.RBTDecoders.helpers.extractBase64Payload(message);
      if (!b64) return false;
      const bytes = window.RBTDecoders.helpers.base64ToBytes(b64);
      return bytes && bytes.length >= 2;
    },
    decode: function (message) {
      try {
        let port = getPort(message);
        const b64 = window.RBTDecoders.helpers.extractBase64Payload(message);
        if (!b64) return { eventType: 'sensative_strips', decoded: { error: 'No payload found', port } };
        const bytes = window.RBTDecoders.helpers.base64ToBytes(b64);
        if (!bytes || bytes.length === 0) return { eventType: 'sensative_strips', decoded: { error: 'Empty payload', port, payload_base64: b64 } };
        const arr = Array.from(bytes);
        if (port === 0 || port === 1) {
          for (const p of [1, 2, 11]) {
            try {
              const decoded = decodeLoraStripsUplink(p, arr);
              return { eventType: 'sensative_strips', decoded: { port: p, decoded } };
            } catch (_) { /* try next */ }
          }
          return {
            eventType: 'sensative_strips_error',
            decoded: { error: 'Failed to decode on ports 1, 2, or 11', payload_base64: b64, payload_hex: arr.map(b => b.toString(16).padStart(2, '0')).join('') },
          };
        }
        const decoded = decodeLoraStripsUplink(port, arr);
        return { eventType: 'sensative_strips', decoded: { port, decoded } };
      } catch (e) {
        return {
          eventType: 'sensative_strips_error',
          decoded: { error: String(e && e.message ? e.message : e), port: getPort(message), payload_base64: window.RBTDecoders.helpers.extractBase64Payload(message) },
        };
      }
    },
    encoders: [
      {
        id: 'set_setting',
        name: 'Set Setting',
        defaultPort: 11,
        schema: [
          { key: 'setting', label: 'Setting', type: 'select', required: true, options: SETTINGS_KEYS.map(k => ({ value: k, label: STRIPS_SETTINGS[k].name })) },
          { key: 'value', label: 'Value (decimal, 0xhex, or Report1|Report2 / INVERT_DOOR|...)', type: 'text', required: true, placeholder: 'e.g. 1000 or TempReport|BatteryReport' },
        ],
        encode: function (params) {
          const rawValue = (params.value == null ? '' : String(params.value)).trim();

          // Advanced mode: if Value is a JSON object, treat each key as a setting name
          // and build one SetSetting command containing multiple setting/value pairs:
          //   {"BASE_POLL_INTERVAL":1000,"TEMP_POLL_INTERVAL":60}
          // => 01 [id/val for BASE_POLL_INTERVAL][id/val for TEMP_POLL_INTERVAL]
          let payloadHex = '';
          if (rawValue && rawValue[0] === '{') {
            try {
              const multi = JSON.parse(rawValue);
              if (multi && typeof multi === 'object' && !Array.isArray(multi)) {
                Object.keys(multi).forEach(function (key) {
                  if (!STRIPS_SETTINGS.hasOwnProperty(key)) {
                    throw new Error('Unknown setting in JSON: ' + key);
                  }
                  payloadHex += encodeSetSettingObj(key, multi[key]);
                });
              } else {
                // Not an object, fall back to single-setting behaviour
                payloadHex = encodeSetSettingObj(params.setting, rawValue);
              }
            } catch (e) {
              // Invalid JSON, fall back to single-setting behaviour
              payloadHex = encodeSetSettingObj(params.setting, rawValue);
            }
          } else {
            // Original behaviour: one setting/value per downlink
            payloadHex = encodeSetSettingObj(params.setting, rawValue);
          }

          const hex = '01' + payloadHex;
          return { port: 11, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'get_setting',
        name: 'Get Setting',
        defaultPort: 11,
        schema: [
          { key: 'setting', label: 'Setting', type: 'select', required: true, options: SETTINGS_KEYS.map(k => ({ value: k, label: STRIPS_SETTINGS[k].name })) },
        ],
        encode: function (params) {
          const hex = '02' + encodeGetSettingObj(params.setting);
          return { port: 11, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'set_profile',
        name: 'Set Profile',
        defaultPort: 10,
        schema: [
          { key: 'profile', label: 'Profile', type: 'select', required: true, options: PROFILE_KEYS.map(k => ({ value: k, label: STRIPS_PROFILES[k].name })) },
        ],
        encode: function (params) {
          const hex = '01' + encodeSetProfileObj(params.profile);
          return { port: 10, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'get_history',
        name: 'Get History',
        defaultPort: 2,
        schema: [
          { key: 'first', label: 'First sequence number', type: 'number', required: true, default: 0 },
          { key: 'last', label: 'Last sequence number', type: 'number', required: true, default: 0 },
        ],
        encode: function (params) {
          const hex = '01' + encodeGetHistoryObj(params.first, params.last);
          return { port: 2, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'unjoin',
        name: 'Unjoin',
        defaultPort: 10,
        schema: [{ key: 'minutes', label: 'Minutes until unjoin', type: 'number', required: true, default: 0 }],
        encode: function (params) {
          const hex = '08' + encodeCmdUnjoinObj(params.minutes);
          return { port: 10, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
      {
        id: 'end_compliance_test',
        name: 'End Compliance Test',
        defaultPort: 224,
        schema: [],
        encode: function () {
          const hex = '06' + encodeEndCompObj();
          return { port: 224, data_hex: hex, data_base64: hexToBase64(hex) };
        },
      },
    ],
  });
})();
