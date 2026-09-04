const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// expo-sqlite uses its bundled wa-sqlite module on the web preview. Keeping
// WASM as an asset also makes the local visual-regression build deterministic.
if (!config.resolver.assetExts.includes('wasm')) {
  config.resolver.assetExts.push('wasm');
}

module.exports = config;
