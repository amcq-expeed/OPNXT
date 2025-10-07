module.exports = {
  extends: ["stylelint-config-standard"],
  plugins: ["stylelint-order"],
  rules: {
    "block-no-empty": true,
    "no-empty-source": true,
    "color-hex-length": "short",
    "selector-max-id": 0,
    "order/properties-order": [],
  },
  ignoreFiles: ["node_modules/**/*", ".next/**/*", "out/**/*"],
};
