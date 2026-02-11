# JS decoder plugins

This folder implements a **client-side decoder/encoder plugin system** for:
- **Uplinks page** (`uplinks.html`) - decode incoming messages
- **Downlink Tools page** (`tools_downlinks.html`) - encode and send downlinks

## How it works

- `decoder_registry.js` exposes `window.RBTDecoders.registerDecoder(...)`
- Each plugin is a JS file that calls `registerDecoder()` once at load
- **Uplinks**: renders a decoder dropdown per message row (and a default decoder selector)
  - You can pin a decoder per-DevEUI (saved in `localStorage`)
- **Downlink Tools**: lists codecs that have `encoders[]` and lets you build/send downlinks

## Add a new decoder (decode only)

1. Create a new file in this folder, e.g. `my_decoder.js`
2. Add it to `uplinks.html` (script tag) **before** `mqtt_messages.js`
3. Register your decoder:

```javascript
(function () {
  'use strict';
  if (!window.RBTDecoders) return;

  window.RBTDecoders.registerDecoder({
    id: 'my_decoder',
    name: 'My Decoder',
    // Smaller = earlier in Auto selection (optional)
    priority: 200,
    // If true, Auto will not choose it (optional)
    excludeFromAuto: false,
    // Optional: return true if this decoder applies
    canDecode: function (message) {
      // Use message.topic, message.data, or payload bytes to decide
      return false;
    },
    // Required: return decoded object or { eventType, decoded }
    decode: function (message) {
      return { eventType: 'my_event', decoded: { hello: 'world' } };
    },
  });
})();
```

## Add a decoder with encoder support (decode + encode)

To support downlink encoding, add an `encoders` array:

```javascript
window.RBTDecoders.registerDecoder({
  id: 'my_codec',
  name: 'My Codec',
  decode: function (message) { /* ... */ },
  
  // NEW: Optional array of downlink encoders
  encoders: [
    {
      id: 'set_config',
      name: 'Set Configuration',
      defaultPort: 10,
      // Schema defines form inputs (rendered automatically in tools_downlinks.html)
      schema: [
        {
          key: 'param1',
          label: 'Parameter 1',
          type: 'text',  // or 'number', 'select'
          required: true,
          placeholder: 'Enter value',
          default: '0',
        },
        {
          key: 'param2',
          label: 'Parameter 2',
          type: 'select',
          required: true,
          options: [
            { value: 'option1', label: 'Option 1' },
            { value: 'option2', label: 'Option 2' },
          ],
        },
      ],
      // Must return { port, data_hex } or { port, data_base64 } or both
      encode: function (params) {
        // params contains values from schema fields
        const hex = '01AABBCCDD';
        return {
          port: 10,
          data_hex: hex,
          data_base64: btoa(String.fromCharCode(...new Uint8Array(hex.match(/.{1,2}/g).map(b => parseInt(b, 16)))))
        };
      },
    },
  ],
});
```

## Helpers available

`window.RBTDecoders.helpers` provides:

- `extractBase64Payload(message)`
- `base64ToBytes(b64)`
- `bytesToHex(bytes)`
- `extractDevEui(message)`

## Examples

- `sensative_strips.js` - Complete codec (decode + 5 encoders: Set Setting, Get Setting, Set Profile, Get History, Unjoin)
- `radiobridge.js` - Decode only (RadioBridge uplink decoder)
- `raw.js` - Decode only (fallback raw hex/base64 viewer)

