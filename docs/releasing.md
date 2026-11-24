# SAMI Desktop releases

The desktop app and CLI have independent versions. Desktop `0.3.0` uses the published CLI `0.2.4` and protocol v1. The runtime manifest records the pinned wheel, its SHA-256, and the expected desktop artifact names.

## Validate a candidate

From `ui/`, run `npm ci`, `npm test`, `npm run build`, and `npm run test:desktop` with Node.js 24. On headless Linux, run the desktop test under `xvfb-run -a`. The test exercises file picking, multiple dropped PDFs, a folder batch, Markdown and PDF previews, export, and cancellation. With `SAMI_TEST_REAL_CLI_HOME` pointing at a ready CLI installation, it runs the batch against that CLI.

| Platform | Package | Acceptance checks |
|---|---|---|
| Native Windows x64 | `npm run package:win` | Run the NSIS installer with the pinned CLI. Check Installed apps, Start, and the desktop shortcut. Launch from the installed path. Uninstall the app and verify `sami --version`. |
| Linux x64 | `npm run package:linux` | Verify the AppImage and its application menu entry on Arch Linux and Debian 13. Include Arch's `openssl-3` runtime when validating on an OpenSSL 4 system. Check that UI removal preserves the CLI and results. |

Run `--smoke-test` on each packaged executable to verify Electron and the bundled renderer start. For an AppImage host without FUSE, run it with `--appimage-extract-and-run`.

## Publish

1. Merge the validated candidate into `main` and tag that commit `v0.3.0`.
2. The desktop release workflow builds Windows and Linux packages and creates a draft with the packages, installers, manifest, and `SHA256SUMS`.
3. Verify the draft's downloads and repeat the installation checks with those exact artifacts before publishing. The installers consume these prebuilt files and the original CLI wheel.
