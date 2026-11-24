# SAMI design assets

The app uses the supplied SAMI artwork across themes and desktop platforms.

| Context | Asset |
|---|---|
| Small UI or title icon | `icons/sami-icon-simple.svg` or a PNG at 32 px or below |
| App branding | `icons/sami-icon.svg` or a PNG at 48 px or above |
| Windows installer, app, and shortcuts | `icons/sami-icon.ico` |
| Linux app menu | `icons/sami-icon-128.png` |

The theme tokens and CSS live in `../src/styles/`. The English and Spanish catalog lives in `../src/locales/i18n.json`. The stylesheet uses the declared local font stacks so the app can run offline.
