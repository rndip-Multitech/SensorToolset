// RadioBridgeTools - client-side decoder registry
// Drop new decoders in this folder and call window.RBTDecoders.registerDecoder(...)

(function (global) {
  'use strict';

  /** @type {Map<string, any>} */
  const registry = new Map();

  function assert(cond, msg) {
    if (!cond) throw new Error(msg);
  }

  function safeJsonParse(str, fallback) {
    try {
      return JSON.parse(str);
    } catch {
      return fallback;
    }
  }

  function bytesToHex(bytes) {
    if (!bytes) return '';
    let hex = '';
    for (let i = 0; i < bytes.length; i++) {
      const b = bytes[i] & 0xff;
      hex += b.toString(16).padStart(2, '0');
    }
    return hex;
  }

  function base64ToBytes(b64) {
    if (!b64 || typeof b64 !== 'string') return null;
    try {
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return bytes;
    } catch {
      return null;
    }
  }

  // Try to find a base64 payload in different common shapes.
  function extractBase64Payload(message) {
    const d = message && message.data;
    if (!d) return null;
    // MultiTech LNS MQTT format (current app)
    if (typeof d.data === 'string') return d.data;
    // TTN v3 (common)
    if (d.uplink_message && typeof d.uplink_message.frm_payload === 'string') return d.uplink_message.frm_payload;
    // TTN v2 (common)
    if (typeof d.payload_raw === 'string') return d.payload_raw;
    // Generic
    if (typeof d.frm_payload === 'string') return d.frm_payload;
    return null;
  }

  function extractDevEui(message) {
    const d = message && message.data;
    if (d && typeof d.deveui === 'string' && d.deveui) return d.deveui;
    // Fallback: parse lora/<DevEUI>/up style topics
    const topic = message && message.topic;
    if (typeof topic === 'string') {
      const parts = topic.split('/');
      if (parts.length >= 2) return parts[1];
    }
    return null;
  }

  function registerDecoder(decoder) {
    assert(decoder && typeof decoder === 'object', 'Decoder must be an object');
    assert(typeof decoder.id === 'string' && decoder.id.trim(), 'Decoder.id must be a non-empty string');
    assert(typeof decoder.name === 'string' && decoder.name.trim(), 'Decoder.name must be a non-empty string');
    assert(typeof decoder.decode === 'function', 'Decoder.decode must be a function');
    if (decoder.canDecode && typeof decoder.canDecode !== 'function') {
      throw new Error('Decoder.canDecode must be a function if provided');
    }
    // Validate encoders if provided
    if (decoder.encoders !== undefined) {
      assert(Array.isArray(decoder.encoders), 'Decoder.encoders must be an array if provided');
      decoder.encoders.forEach((enc, idx) => {
        assert(enc && typeof enc === 'object', `Encoder[${idx}] must be an object`);
        assert(typeof enc.id === 'string' && enc.id.trim(), `Encoder[${idx}].id must be a non-empty string`);
        assert(typeof enc.name === 'string' && enc.name.trim(), `Encoder[${idx}].name must be a non-empty string`);
        assert(typeof enc.encode === 'function', `Encoder[${idx}].encode must be a function`);
        if (enc.schema && !Array.isArray(enc.schema)) {
          throw new Error(`Encoder[${idx}].schema must be an array if provided`);
        }
      });
    }
    registry.set(decoder.id, decoder);
  }

  function listDecoders() {
    return Array.from(registry.values()).sort((a, b) => {
      const pa = typeof a.priority === 'number' ? a.priority : 1000;
      const pb = typeof b.priority === 'number' ? b.priority : 1000;
      return pa - pb;
    });
  }

  function getDecoder(id) {
    return registry.get(id) || null;
  }

  function pickAutoDecoder(message) {
    const decoders = listDecoders().filter((d) => !d.excludeFromAuto);
    for (const d of decoders) {
      try {
        if (!d.canDecode) return d; // if no predicate, it can decode anything (acts as fallback)
        if (d.canDecode(message)) return d;
      } catch {
        // ignore decoder errors during probing
      }
    }
    return null;
  }

  // Standardize decoder output into { eventType, decoded }.
  function normalizeDecodedOutput(out) {
    if (!out || typeof out !== 'object') {
      return { eventType: 'unknown', decoded: out };
    }
    if ('eventType' in out && 'decoded' in out) return out;
    if ('event' in out) return { eventType: out.event, decoded: out };
    if ('message_type' in out) return { eventType: out.message_type, decoded: out };
    return { eventType: 'decoded', decoded: out };
  }

  // Get all decoders that have encoders
  function listDecodersWithEncoders() {
    return listDecoders().filter((d) => d.encoders && Array.isArray(d.encoders) && d.encoders.length > 0);
  }

  // Get encoder by decoder id and encoder id
  function getEncoder(decoderId, encoderId) {
    const decoder = getDecoder(decoderId);
    if (!decoder || !decoder.encoders) return null;
    return decoder.encoders.find((e) => e.id === encoderId) || null;
  }

  // Public API
  global.RBTDecoders = {
    registerDecoder,
    listDecoders,
    getDecoder,
    pickAutoDecoder,
    normalizeDecodedOutput,
    listDecodersWithEncoders,
    getEncoder,
    helpers: {
      safeJsonParse,
      base64ToBytes,
      bytesToHex,
      extractBase64Payload,
      extractDevEui,
    },
  };
})(window);

