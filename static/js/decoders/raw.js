// Raw payload decoder (always available)
(function () {
  'use strict';
  if (!window.RBTDecoders) return;

  window.RBTDecoders.registerDecoder({
    id: 'raw',
    name: 'Raw (base64/hex)',
    priority: 9999,
    canDecode: function (message) {
      // Always decodes (fallback)
      return true;
    },
    decode: function (message) {
      const b64 = window.RBTDecoders.helpers.extractBase64Payload(message);
      const bytes = window.RBTDecoders.helpers.base64ToBytes(b64);
      const hex = window.RBTDecoders.helpers.bytesToHex(bytes || []);
      return {
        eventType: 'raw',
        decoded: {
          has_payload: !!b64,
          payload_base64: b64 || null,
          payload_hex: hex || null,
          payload_len: bytes ? bytes.length : 0,
        },
      };
    },
  });
})();

