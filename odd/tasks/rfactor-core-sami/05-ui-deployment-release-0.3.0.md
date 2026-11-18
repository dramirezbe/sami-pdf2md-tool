# 05 — UI deployment and release 0.3.0

Date: 2026-11-18, America/Bogota. Status: specification for future implementation.
Future branch: `feat/0_3_0_sami_ui`. Units U10–U11.
Depends on [04 — Electron application](04-ui-electron-application-0.3.0.md) and a published/tested CLI `0.2.x`.
General entry point: [index](2026-11-18_10-31-38_sami-refactor-plan.md).

## Stage outcome

Complete installation runs CLI → health → UI. On completion, the user double-clicks the executable or shortcut and can convert without a console, manual activation, or pending installations. CLI remains separately installable and usable.

## Files

| Current/future file | Work |
|---|---|
| `ui/electron-builder.yml` | Product, stable identity, icons, Windows NSIS target; Linux according to tested baseline. |
| `ui/package.json`, `package-lock.json` | Version `0.3.0`, consistent scripts and packaging dependencies. |
| `packaging/windows/` | Minimal hooks for CLI dependency, health, and registration; avoid duplicating bootstraps. |
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
| Health | Query registered executable. | `ready/degraded` advance. GPU failure with ready CPU does not block. Incomplete core requires installation repair. |
| UI | Install the release's Electron application. | Intact package, verified version/protocol. |
| Integration | Registration, shortcuts, and launchers. | Existing, unambiguous targets; no shortcuts to temporary files. |
| Finish | Graphical smoke and CLI query. | Announce complete only when double-click operation and conversion work without dependency preparation. |

If CLI fails, do not report successful UI installation. If UI fails, preserve working CLI and allow retrying the graphical stage. Model preparation finishes before announcing readiness even if performed in a supervised background job.

### Windows 11

Use electron-builder/NSIS for per-user graphical distribution. Proposed stable location: `%LOCALAPPDATA%\Programs\SAMI\ui`; CLI retains its registered location. The Electron package does not require users to prepare Node/Python/models: Electron bundles Node and CLI bootstrap prepares Python/models.

| Integration | Required detail |
|---|---|
| Desktop | `SAMI.lnk`, own icon, stable graphical executable target. Resolve the actual Known Folder, including redirected/OneDrive desktop. |
| Start | `SAMI` entry in user Programs; verify menu and OS search after registration. |
| Double-click | UI without a console, independent of cwd or Explorer's refreshed `PATH`. Health/CLI use the registered absolute path. |
| `PATH` | Add stable launcher directory to user entries without duplicates/replacement. Keep `sami`; proposed graphical launcher `sami-gui`. |
| Registration | Version/uninstaller and stable application identity across updates. |
| Update | No duplicate shortcuts/installations. Preserve configuration and diagnostics for unchanged components. Maintain graphical-version rollback. |
| UI-only uninstall | Remove owned UI application/shortcuts/registration; preserve CLI and documents. Do not remove `sami` from `PATH` if CLI remains installed. |
| Complete uninstall | Coordinate dependencies, remove only owned integration, preserve PDFs/results; explicit cache-cleanup policy. |

Update persistent environment and notify the OS; bootstrap may refresh its own session's `PATH`, but cannot promise to modify already running terminal processes. UI never depends on that refresh to locate CLI.

Start menu presence does not mean starting at login. Do not add autostart or taskbar pinning as unrequested requirements. Per-user installation does not request privileges except a driver step explicitly requested by the user.

### Linux and macOS

For Debian-based Linux, package an AppImage or Debian package **after testing it on the CLI baseline**; register the application and `.desktop` launcher where appropriate. The requirement is a usable installation, not a particular unverified file extension without OS runtime/graphics checks. Linux desktop shortcuts may depend on desktop environment and permissions; document actual scope.

macOS is secondary/nonblocking. If distributed, test package/app and installed CLI access on that platform without claiming unverified Windows/Linux equivalence.

### U10 tests and completion

1. Clean Windows installation without Python/Node; three ready CLI modes and double-click UI.
2. Add UI to published healthy CLI without repeating downloads/diagnostics; detect incompatible versions before activating an invalid pair.
3. Normal/redirected desktop, Unicode/spaced username, Start, previous `PATH`, and a shell opened before installation.
4. GPU failure → warning/CPU with usable UI. CLI/UI installation failure → clear outcome and limited rollback.
5. Reinstall/update without duplicates; UI-only removal preserves `sami`; complete uninstall preserves documents.
6. Matrix Linux: run package, open window, locate CLI, convert, open folder, and actual native drag.

Record identity/versions/paths and commands; attach evidence of double-click operation and shortcuts using the actual package. **Rollback:** remove/restore only UI and its shortcuts; CLI remains available.

## U11 — CI and graphical release 0.3.0

### Independent versions

| Component | Version/validation |
|---|---|
| Electron UI | `0.3.0` in `package.json` and lock. |
| Python CLI | Exact tested `0.2.x`, normally `0.2.0` if no fixes were needed. Do not rename an unchanged wheel to `0.3.0`. |
| Product manifest | `0.3.0` with identities of both components and protocol. |
| Repository release/tag | `v0.3.0`, UI commit already merged into `main`. |

If UI reveals a CLI gap, fix and publish a CLI version with a new identity, updating the dependency. Do not replace `0.2.0` bytes. Bootstrap does not use `latest` to guess CLI dependency because Latest will point to the UI release.

### Pipeline and publication

1. Complete U08–U11 and update docs/changelog in `feat/0_3_0_sami_ui`, with versions/protocol checked by CI.
2. Merge the PR into `main`; pin candidate SHA and run trial build plus package smoke. Test clean installation and installation over existing CLI using those assets.
3. Create/push annotated tag `v0.3.0` on that merged SHA. Workflow builds from tag and validates versions **per component**, not blind UI=CLI equality.
4. Build required Windows/Linux UI and macOS only if validated; produce checksums and draft. Download the exact published CLI the installer will use and test that actual pairing.
5. Attach UI package, bootstraps, manifest, `SHA256SUMS`, and `0.3.0` notes. The CLI wheel may be referenced from its original release; do not rebuild the same version with different bytes.
6. Pass U10 with final assets; publish `0.3.0` as Latest and verify public `irm/curl` URLs, complete installation, and CLI-only installation. Keep `v0.2.0` accessible.
7. Record SHA/tag/run, component pair, tested matrix, outcomes, and rollback. Failed builds remain drafts; never move tags or replace consumed stable releases.

Proposed assets: `SAMI-0.3.0-win-x64-setup.exe`, tested Linux package, `install.ps1`, `install.sh`, manifest, and checksums. Exact names must match actual electron-builder output. Node/npm are not runtime prerequisites the user must install.

### Final acceptance

The user installs through `irm`, waits for CLI installation/health, completes UI setup, and opens from desktop/Start or `.exe`. They can add/drag PDFs/folders, choose mode/output, see progress/previews, cancel, and open/export results. All processing/fallback depends on the published CLI. Uninstalling UI does not prevent continued CLI `0.2.x` use.

Sources: [electron-builder NSIS](https://www.electron.build/v26/docs/nsis/), [Start menu shortcuts](https://learn.microsoft.com/en-us/windows/win32/shell/how-to-add-shortcuts-to-the-start-menu), [Known Folders](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid), [Windows environment variables](https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables), [release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

This document describes future actions; saving it does not create installers, branches, tags, or releases.
