# 02 — Persisted diagnostics, runtimes, and complete installation

Date: 2026-11-18, America/Bogota. Status: specification for future implementation.
Future branch: `refactor/0_2_0_sami_cli`. Units U03–U05.
Depends on [01 — contracts/engines](01-cli-contracts-engines-outputs.md).
Next: [03 — CLI and release 0.2.0](03-cli-batches-validation-release-0.2.0.md).

## Stage outcome

An installation that leaves all three modes usable and a validated CPU path. Acceleration is optional: on failure, the user receives a warning and conversion continues on CPU in the same mode. Expensive analysis happens during installation; subsequent executions consult a persisted profile and a brief health check.

## Files and boundaries

| Current/future file | Work |
|---|---|
| `sami/hardware.py` | OS/CPU/RAM/GPU/driver inventory without requiring Torch to exist already. |
| `sami/compatibility.py` | Atomic reads/writes, schema, and lightweight profile validation. |
| `sami/runtime.py` | Installation planning/execution, environment selection, and offline models. |
| `sami/worker.py` | Internal entry point for executing an adapter inside its selected runtime. Not exposed as a UI function. |
| `sami/processes.py` | Own process/tree, output, control, timeout, cancellation, and fallback. |
| `sami/cli.py` | Dispatch for `setup`, `health`, `doctor`, and coordinator invocation; no diagnostics on import. |
| `packaging/runtime-manifest.json`, `packaging/constraints/` | Versions, sources, checksums, models, and tested recipes per platform/backend. |
| `install.sh`, `install.ps1`, `setup.sh` | Thin, consistent bootstraps without repeated compatibility logic. |
| `pyproject.toml`, `requirements.txt`, chosen lock | Lightweight base and reproducible runtimes; prevent a generic installer from replacing GPU Torch with CPU Torch or vice versa. |
| `tests/test_hardware.py`, `test_compatibility.py`, `test_runtime.py`, `test_processes.py` | State, recovery, and contract tests without real hardware. |
| `tests/integration/` | Real processes and bootstraps in acceptance environments, separate from fast tests. |

## U03 — Inventory and persisted profile

### Collection during installation

Separate `detect_hardware()`, which does not modify the system, from `validate_runtime()`, which needs prepared components. Inventory OS/version/distribution/architecture and WSL/container, physical/logical cores/quotas, available RAM, identifiable GPUs, total/free VRAM, and drivers. Include free disk space and destination permissions.

Use available APIs/commands with timeouts and bounded output. Inventory sources may include OS information, psutil, NVIDIA SMI, AMD SMI/rocminfo, or system mechanisms. A missing tool means unknown data; it does not require installing global utilities to detect the rest of the machine.

Distinguish four pieces of evidence: physical GPU, driver, runtime, and inference engine. On ROCm, `torch.cuda` alone does not identify NVIDIA. Installation tests must check where the actual VLM executes, not just a Torch operation. Persist negative results too.

### Installation state, not repository files

Proposed locations:

| Data | Windows 11 | Debian-based Linux |
|---|---|---|
| Application/launcher | Stable location under `%LOCALAPPDATA%\Programs\SAMI\cli`. | `~/.local/bin/sami` launcher, private environment under SAMI state. |
| State/runtimes/models | `%LOCALAPPDATA%\SAMI`. | `$XDG_DATA_HOME/sami`, or `~/.local/share/sami`. |
| Override | `SAMI_HOME` changes state/runtimes; register the actual executable location. | Same. Adopt a valid previous `~/.sami` installation before migrating/copying caches. |

Do not derive CLI location from cwd or the first `PATH` result for the future UI. Record `installation.json` with identity, absolute executable, version, and protocol. Separate this record from GPU diagnostics and PDF results.

Proposed internal files: `installation.json`, `compatibility.json`, its previous valid copy, and `logs/`. Models/caches do not belong in Git or the text diagnostic report. Resolve suitable macOS paths only within its secondary scope.

### Minimum persisted schema

| Field | Contents |
|---|---|
| `schema_version`, `installation_id` | Schema version and stable local identity. |
| `validated_at`, `cli_version`, `protocol_version` | Date and versions of full validation. |
| `platform` | OS, version, architecture, and environment features. |
| `hardware` | CPU/RAM and GPU identities; distinguish absence from unknown data. |
| `runtimes` | Path, backend, version, component fingerprint, and status per environment. |
| `modes` | `fast/balanced/quality`, validated CPU path, and actually tested accelerators. |
| `models` | Identities/versions, paths, and installation integrity evidence. |
| `warnings`, `failures` | Code, reason, and affected fingerprint; distinguish transient from permanent. |

Save after validation, with temporary write and atomic replacement plus a valid backup. An interrupted installer does not replace a ready profile with a half-written one. An unknown future schema does not trigger deletion or automatic reinstallation during health checks.

### Fast health check

`health_check()` reads the record/profile and checks schema, required paths, and lightweight fingerprints for the chosen mode. No network, Torch/Marker, full model hashes, or inference server. An optional OS query has a timeout within a global budget; do not accumulate unlimited waits per provider.

Measurement target: less than one second of added cost on a healthy installation. Measure multiple runs, reporting median/p95 and environment; do not treat it as an already achieved guarantee. Help and version do not run this health check at all.

Invalidate only what evidence shows has changed. Do not expire by time or repeat failed diagnostics with the same fingerprint for every file. Checking free RAM/VRAM before reserving resources does not invalidate compatibility.

| Health | Meaning | `sami health` exit code |
|---|---|---|
| `ready` | Core and all three CPU paths ready; selected backend usable. | 0 |
| `degraded` | GPU unusable, but CPU complete and validated. | 0, with warning |
| `repair_required` | Required component/core missing or unrecoverable record. | 3, precise reason |

Health JSON schema: `protocol_version`, `installation_id`, `cli_version`, `status`, `modes`, `selected_device`, `warnings`, `repair_reasons`. A GPU failure alone never yields `repair_required`. `doctor` explains stored data; it is not an alias for deep diagnostics.

### U03 tests and completion

Simulate ready/negative/corrupt profiles, backups, unknown schema, GPU changes, and intact CPU runtime. Block network/heavy imports in health tests. Check negative-result reuse and that the second invocation does not repeat deep probes. Do not persist sensitive data from the complete environment.

**Rollback:** retain a valid copy and executable record; revert the schema through explicit migration, never by deleting models/documents.

## U04 — Environments, supervisor, and fallback

### Environment preparation

Maintain a lightweight CLI base and separate worker environments when CPU and GPU need incompatible variants. Complete installation includes the CPU runtime and models for both Marker profiles, even with a GPU present. `fast` uses lightweight extraction without importing models.

Use uv-managed Python as the initial bootstrap proposal, avoiding a prerequisite Python installation. Pin the Python version verified in U00, compatible with the current project. Record exact versions and sources in manifest/locks; do not resolve `latest` on every invocation or compile large dependencies as an automatic fallback.

Each worker runtime receives the same SAMI contract/adapter version as the CLI coordinator. Launch it by absolute path, with a JSON request and explicit model/backend configuration. Reuse the worker per batch where feasible; do not load models per page or PDF unnecessarily.

### Installation state machine

`planned → preparing → validating → ready`, with recoverable `failed`. Download tasks may run in a supervised background job, but the bootstrap waits for validation before announcing success.

1. Read release/manifest and locate compatible existing components.
2. Prepare in staging, verify integrity, and resolve CPU before GPU.
3. Download every required model and perform a minimal conversion per mode during installation.
4. Prepare GPU if compatible and validate the engine's actual device. On failure, warn and retain ready CPU execution.
5. Activate environments and persist record/profile only when consistent. Keep the previous environment until the new one is validated.

For normal use, configure dependencies to use local models without automatic downloads. A missing model is an incomplete installation; do not open a download dialog on the first `quality` conversion.

### Execution fallback

| Situation | Action |
|---|---|
| Machine without a compatible GPU | Normal CPU execution; do not repeat failure warnings about a nonexistent GPU. |
| Health detects a prepared GPU is no longer ready | Warn, use CPU in the same mode, and check only once per batch. |
| GPU fails during startup or inference | Stop the owned GPU attempt/worker, clean its staging, emit `job_retrying`, and retry that document on CPU. |
| GPU fails for a document in the batch | Use CPU for subsequent documents; do not retry GPU per document under the same condition. |
| Invalid/encrypted PDF, output permissions, or full disk | Appropriate document/operation error; do not misclassify it as GPU failure. Continue other documents where appropriate. |

A GPU failure permits **one** CPU retry per document, not a CPU↔GPU loop. If CPU conversion succeeds, conversion exits 0 unless other errors/partials exist. The warning and effective device remain in the result. A failed attempt never replaces a previous output.

Do not permanently disable a GPU because of temporary memory pressure; record reason and scope. Do not repeat the deep test every time the user invokes CLI either. Design recovery using component fingerprints and session state.

### Cancellation and owned processes

The coordinator controls workers and servers started for its installation/job; it does not kill global processes by name. Implement POSIX and Windows without assuming universal `SIGKILL`. On Windows, close the owned process tree through an appropriate OS mechanism; test with real child/grandchild test processes.

Proposed budget: cooperative cancellation and up to 5 s to exit, termination and another 5 s before forced closure. These are operational limits to validate, not waits repeated serially for every PID. Cancellation does not trigger CPU fallback. Do not kill an external pre-existing server that the job does not own.

### U04 tests and completion

Test processes with fragmented stdout, abundant stderr, failure before/during inference, a grandchild, and cancellation. Verify a single CPU output, counters without duplication, cleanup limited to owned processes/staging, and no protocol contamination. Then run real CPU tests for both Marker profiles and at least every GPU combination advertised.

**Rollback:** return to the previous validated runtime; disable only the new environment and retain reusable models. GPU state does not invalidate an intact CPU path.

## U05 — Complete bootstraps, repair, and maintenance

| Future entry point | Behavior |
|---|---|
| `install.sh` / `install.ps1` | Obtain CLI release `0.2.0`, verify assets, prepare Python/environments/all three modes, register location, configure `PATH`, and query health. |
| `setup.sh` | Existing-installation compatibility; delegate preparation to the same flow. Do not retain a divergent runtime recipe. |
| `sami setup` | Explicit preparation/repair entry point; may run deep diagnostics and download. |
| Bootstrap `update` | Prepare the new version without destroying the previous one before validation. |
| Bootstrap `uninstall` | Remove the owned application/integration; preserve PDFs/results. Explicit cache policy. |

In `0.2.0`, do not install UI, graphical NSIS, or shortcuts to a nonexistent executable. On Windows, configure user `PATH` without replacing entries and register the CLI path; help/health must work from a new process with an updated environment. The future UI opens by absolute path without depending on Explorer's environment.

Do not automatically elevate, install drivers, or restart services in the normal flow. If GPU requires a driver, explain the state once and complete CPU setup without blocking. Any privileged driver operation belongs to a separately requested explicit step, independent of having a usable CLI.

Prepare the bootstrap with testable functions: resolve version/artifact, verify, install, activate, and check. Do not download moving `main` code as the engine implementation. The release manifest distinguishes published data from local diagnostics.

### U05 tests and completion

1. Windows 11 and the Debian/Ubuntu matrix from U00, without preinstalled Python or admin privileges for user installation.
2. All modes work with network blocked after installation; help/health prepare nothing.
3. Idempotent reinstallation, Unicode/spaced paths, download failure, insufficient disk space, and interrupted installation.
4. Missing/failed GPU ends with ready CPU and a warning; incomplete CPU installation does not announce success.
5. Update preserves fallback/recovery; uninstall removes only owned components, not PDFs/results.

Record OS, architecture, versions, commands, output, and separate installation/conversion durations. **Completion:** three ready modes, consistent record, fast health check, and accessible CLI; plan 03 still completes batches/release. Do not publish from this unit yet.
