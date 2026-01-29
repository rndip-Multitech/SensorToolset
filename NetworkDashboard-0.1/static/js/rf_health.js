// RF health helpers (RSSI/SNR classification + labels)
(function (global) {
  'use strict';

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function rssiQuality(rssi) {
    if (typeof rssi !== 'number' || !isFinite(rssi)) return null;
    // Typical LoRa RSSI ranges: ~ -40 (very strong) to -120 (weak)
    if (rssi >= -90) return { level: 'good', label: 'Good', hint: 'Strong signal' };
    if (rssi >= -110) return { level: 'ok', label: 'OK', hint: 'Usable signal' };
    return { level: 'poor', label: 'Poor', hint: 'Weak signal – consider moving device or gateway' };
  }

  function snrQuality(snr) {
    if (typeof snr !== 'number' || !isFinite(snr)) return null;
    // Typical LoRa SNR ranges: ~ -20 (bad) to +10 (great)
    if (snr >= 5) return { level: 'good', label: 'Healthy', hint: 'Good link margin' };
    if (snr >= 0) return { level: 'ok', label: 'Marginal', hint: 'Link margin is limited' };
    return { level: 'poor', label: 'Poor', hint: 'Low link margin – expect packet loss' };
  }

  function barsFrom01(x01) {
    const v = clamp(x01, 0, 1);
    if (v >= 0.8) return 5;
    if (v >= 0.6) return 4;
    if (v >= 0.4) return 3;
    if (v >= 0.2) return 2;
    if (v > 0) return 1;
    return 0;
  }

  function rssiBars(rssi) {
    if (typeof rssi !== 'number' || !isFinite(rssi)) return 0;
    // Map [-120..-40] to [0..1]
    const x01 = (rssi - (-120)) / (80);
    return barsFrom01(x01);
  }

  function snrBars(snr) {
    if (typeof snr !== 'number' || !isFinite(snr)) return 0;
    // Map [-20..10] to [0..1]
    const x01 = (snr - (-20)) / (30);
    return barsFrom01(x01);
  }

  global.RBTRFHealth = {
    rssiQuality,
    snrQuality,
    rssiBars,
    snrBars,
  };
})(window);

