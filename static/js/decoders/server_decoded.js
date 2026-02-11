// Use server-provided data_decoded (legacy / debugging)
(function () {
  'use strict';
  if (!window.RBTDecoders) return;

  window.RBTDecoders.registerDecoder({
    id: 'server_decoded',
    name: 'Server decoded (data_decoded)',
    priority: 50,
    excludeFromAuto: true, // don't let "Auto" pick this (server currently assumes RadioBridge)
    canDecode: function (message) {
      return !!(message && message.data && message.data.data_decoded);
    },
    decode: function (message) {
      const dd = message && message.data ? message.data.data_decoded : null;
      const eventType =
        (dd && (dd.event || dd.message_type)) ? (dd.event || dd.message_type) : 'server_decoded';
      return { eventType, decoded: dd };
    },
  });
})();

