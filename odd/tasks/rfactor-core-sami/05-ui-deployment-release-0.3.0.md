# 05 — UI deployment and release 0.3.0

Date: 2026-11-18, America/Bogota. Status: specification for future implementation.
Future branch: `feat/0_3_0_sami_ui`. Units U10–U11.
Depends on [04 — Electron application](04-ui-electron-application-0.3.0.md). Validate it with [SAMI CLI `0.2.4`](https://github.com/dramirezbe/sami-pdf2md-tool/releases/tag/v0.2.4) and protocol v1 as the initial pair.
General entry point: [index](2026-11-18_10-31-38_sami-refactor-plan.md).

## Stage outcome

Complete installation runs CLI → health → UI using prebuilt release assets. The user opens SAMI from the desktop or application menu and can convert without a console or pending setup. Ship a native Windows installer and a Linux AppImage tested on Arch Linux and a Debian-based distribution. The CLI remains separately installable.

## Files

| Current/future file | Work |
|---|---|
| `ui/electron-builder.yml` | Product identity, imported icons from `ui/assets/icons/`, a native Windows NSIS installer, and a Linux AppImage. |
| `ui/package.json`, `package-lock.json` | Version `0.3.0`, consistent scripts and packaging dependencies. |
| `packaging/windows/` | Minimal hooks for CLI dependency, health, and registration; avoid duplicating bootstraps. |
| `packaging/linux/` | AppImage installation and per-user application menu entry and icon. |
| `install.ps1`, `install.sh` | Add CLI-only/complete/UI-on-existing-installation selection. Same version resolution and checks. |
| `packaging/runtime-manifest.json` | Graphical product `0.3.0`, exact compatible CLI version, protocol, artifacts/checksums. |
| `.github/workflows/ci.yml`, `release.yml` | UI build/smoke, component-pair validation, and graphical release. |
| `.gitignore` | `node_modules` and UI outputs; retain lock/config/source assets. |
| `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/releasing.md` | Install, update, repair, and use UI with a versioned CLI. |
| `ui/tests/`, `tests/integration/` | Installation/process matrix and double-click operation without development dependencies. |

## U10 — Installation and desktop integration

### One installation implementation

Proposed bootstrap components: `cli`, `all`, and `ui`. In `0.3.0`, complete installation uses `all`; `cli` remains available. Document names/syntax after parser implementation. Both `irm` and the downloadable `.exe` invoke the same verified operations.

| Step | Action | Progression rule |
|---|---|---|
| Resolve | Read graphical manifest and local record. | Pin UI `0.3.0`, exact tested CLI, and compatible protocol. |
| CLI | Install if absent; reuse if compatible; update recoverably if necessary. | Three modes and CPU fallback ready. Do not repeat deep diagnostics for a healthy CLI. |
| Health | Query registered executable. | Advance when all modes report a ready CPU path. GPU failure with a ready CPU path leaves the install usable. |
| UI | Install the release's Electron application. | Intact package, verified version/protocol. |
| Integration | Registration, shortcuts, and launchers. | Existing, unambiguous targets; no shortcuts to temporary files. |
| Finish | Graphical smoke and CLI query. | Announce complete only when double-click operation and conversion work without dependency preparation. |

If CLI fails, do not report successful UI installation. If UI fails, preserve working CLI and allow retrying the graphical stage. Model preparation finishes before announcing readiness even if performed in a supervised background job.

Keep a progress indicator and a plain-language step label visible during downloads, CLI and model preparation, verification, UI installation, and shortcut registration. Show measured progress when available and indeterminate activity with elapsed time otherwise. Explain a prolonged wait and show clear terminal outcomes. Use English and Spanish in the graphical installer.

### Windows 11

Use electron-builder/NSIS for per-user graphical distribution. Proposed stable location: `%LOCALAPPDATA%\Programs\SAMI\ui`; CLI retains its registered location. The Electron package does not require users to prepare Node/Python/models: Electron bundles Node and CLI bootstrap prepares Python/models.

Use the imported `sami-icon.ico` for the installer, installed app, and Windows shortcuts.

| Integration | Required detail |
|---|---|
| Desktop | `SAMI.lnk`, own icon, stable graphical executable target. Resolve the actual Known Folder, including redirected/OneDrive desktop. |
| Start | `SAMI` entry in user Programs; verify menu and OS search after registration. |
| Double-click | UI without a console, independent of cwd or Explorer's refreshed `PATH`. Health/CLI use the registered absolute path. |
| `PATH` | Add stable launcher directory to user entries without duplicates/replacement. Keep `sami`; proposed graphical launcher `sami-gui`. |
| Registration | Show SAMI in Windows Settings under **Apps → Installed apps**, with the app icon, version, and uninstall action. Keep a stable application identity across updates. |
| Update | No duplicate shortcuts/installations. Preserve configuration and diagnostics for unchanged components. Maintain graphical-version rollback. |
| UI-only uninstall | Remove owned UI application/shortcuts/registration; preserve CLI and documents. Do not remove `sami` from `PATH` if CLI remains installed. |
| Complete uninstall | Coordinate dependencies, remove only owned integration, preserve PDFs/results; explicit cache-cleanup policy. |

Update persistent environment and notify the OS; bootstrap may refresh its own session's `PATH`, but cannot promise to modify already running terminal processes. UI never depends on that refresh to locate CLI.

Start menu presence does not mean starting at login. Do not add autostart or taskbar pinning as unrequested requirements. Per-user installation does not request privileges except a driver step explicitly requested by the user.

### Linux and macOS

Distribute a prebuilt **AppImage**. Validate the published AppImage and the exact installed CLI on **Arch Linux** and at least one named **Debian-based distribution** with a graphical session.

The Linux bootstrap installs the AppImage at a stable per-user location and registers a `.desktop` entry with the imported SAMI PNG icon in the user application menu. Launch the installed AppImage from that menu with the registered CLI path. Verify that updates keep a single menu entry and that UI removal removes that entry and its icon while preserving the CLI and generated documents.

macOS is secondary/nonblocking. If distributed, test package/app and installed CLI access on that platform without claiming unverified Windows/Linux equivalence.

### U10 tests and completion

1. Clean native Windows installation with no development tools installed. Check three ready CLI modes, the installed-app registration and icon, and launch from the desktop and Start menu.
2. Add UI to published healthy CLI without repeating downloads/diagnostics; detect incompatible versions before activating an invalid pair.
3. Normal/redirected desktop, Unicode/spaced username, Start, previous `PATH`, and a shell opened before installation.
4. GPU failure → warning/CPU with usable UI. CLI/UI installation failure → clear outcome and limited rollback.
5. Reinstall/update without duplicates; UI-only removal preserves `sami`; complete uninstall preserves documents.
6. On Arch Linux and the selected Debian-based baseline, install from the published AppImage through the bootstrap. Launch SAMI from the application menu, verify the icon, locate the CLI, convert, open the result folder, and test native drag and drop.
7. Run the published Windows and Linux installers with Node.js, npm, pnpm, and the source checkout absent. Check visible progress through preparation, verification, and registration.

Record identity/versions/paths and commands; attach evidence of double-click operation and shortcuts using the actual package. **Rollback:** remove/restore only UI and its shortcuts; CLI remains available.

## U11 — CI and graphical release 0.3.0

### Independent versions

| Component | Version/validation |
|---|---|
| Electron UI | `0.3.0` in `package.json` and lock. |
| Python CLI | Start with `0.2.4` and pin the exact published version that passes the UI platform matrix. |
| Product manifest | `0.3.0` with identities of both components and protocol. |
| Repository release/tag | `v0.3.0`, UI commit already merged into `main`. |

If UI reveals a CLI gap, publish a new CLI version and update the dependency. Bootstrap looks up the exact CLI version in the UI manifest. The Latest release can point to the UI.

### Pipeline and publication

1. Complete U08–U11 and update docs/changelog in `feat/0_3_0_sami_ui`, with versions/protocol checked by CI.
2. Merge the PR into `main`; pin candidate SHA and run trial build plus package smoke. Test clean installation and installation over existing CLI using those assets.
3. Create/push annotated tag `v0.3.0` on that merged SHA. Workflow builds from tag and validates versions **per component**, not blind UI=CLI equality.
4. Build the Windows installer on a native Windows CI runner and the AppImage on a Linux runner. Include the compiled renderer, translations, and preview assets in both packages. Test the packages with the exact published CLI on each target platform. Build macOS only if validated.
5. Publish the prebuilt packages, bootstraps, manifest, `SHA256SUMS`, and `0.3.0` notes as GitHub Release assets. Reference the exact CLI wheel from its original release. The installer downloads and verifies the packaged app. Node.js, npm, pnpm, and the renderer build run in development or CI.
6. Pass U10 with final assets, publish `0.3.0` as Latest, and verify public `irm/curl` URLs, complete installation, and CLI-only installation. Keep the pinned CLI release accessible.
7. Record SHA/tag/run, component pair, tested matrix, outcomes, and rollback. Failed builds remain drafts; never move tags or replace consumed stable releases.

Proposed package names are `SAMI-0.3.0-win-x64-setup.exe` and `SAMI-0.3.0-linux-x64.AppImage`. Record the actual electron-builder output names and checksums in the manifest.

### Final acceptance

On Windows, install with `irm` or the setup executable, find SAMI in Installed apps, and open it from the desktop or Start menu. On Arch and the Debian-based baseline, install the AppImage with the bootstrap and open SAMI from the application menu. The installed app supports the complete workflow in English and Spanish and in light and dark mode. The user can stage several PDFs or folders, start the batch manually, follow progress, cancel, and open or export results. UI removal preserves access to the CLI and prior results.

Sources: [electron-builder NSIS](https://www.electron.build/v26/docs/nsis/), [Start menu shortcuts](https://learn.microsoft.com/en-us/windows/win32/shell/how-to-add-shortcuts-to-the-start-menu), [Known Folders](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid), [Windows environment variables](https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables), [release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

This document describes future actions; saving it does not create installers, branches, tags, or releases.
