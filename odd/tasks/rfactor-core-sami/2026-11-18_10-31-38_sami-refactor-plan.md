# SAMI implementation index for the CLI and UI 0.3.0

Opened: 2026-11-18 10:31:38. Plan split: 2026-11-18 11:39:08, America/Bogota (UTC−05:00).
The published CLI `0.2.4` provides the initial integration baseline for UI `0.3.0`. Start with U08–U09 for the desktop workflow, then use U10–U11 to validate and publish the packaged UI on native Windows, Arch Linux, and a Debian-based distribution. [CLI 0.2.4 release](https://github.com/dramirezbe/sami-pdf2md-tool/releases/tag/v0.2.4)

## Historical CLI baseline at 6452f12

| Unit | Status | Evidence / next action |
|---|---|---|
| U00 | In progress; incomplete. | See [U00/U01 runtime and contract evidence](U00-U01-evidence.md). Baseline source files at `6452f12` and branch base `43007b5` compare identical for production paths. Both Marker profiles completed on two five-page PDFs in the locked Python 3.12 CPU environment; extracted pipeline outputs match baseline bytes. The fast engine was separately measured and is not the 15.7-second legacy Marker fast result. CPU path was explicitly configured for Torch, Surya, and llama.cpp. Native Windows and broader Debian/Ubuntu evidence remain unavailable. |
| U01 | Implementation in progress; incomplete. | Added validated contracts and explicit wire representations in `sami/contracts.py`, protocol 1 JSONL events in `sami/events.py`, and wired the public `fast`/`balanced`/`quality` modes through deferred adapters and job/run results. End-to-end fast-engine and Marker CLI runs emit parseable JSONL; Marker retains baseline output hashes. Twenty-five focused tests pass. Remaining: complete cancellation event guarantees, output safety, and plan 01 acceptance review. |

This baseline recorded 25 passing tests with `.venv/bin/python -m unittest discover -s tests -v` and a clean `git diff --check`. Runtime commands, environments, and artifact paths are in the evidence record. [U00/U01 evidence](U00-U01-evidence.md)

## Historical CLI acceptance checklist

This checklist records gaps at the historical baseline. Use the published release and the platform tests in plans 04 and 05 for the current UI handoff.

| Unit | Outstanding evidence or behavior | Relevant implementation plan |
|---|---|---|
| U00 | Native Windows 11 CPU conversion and inference-server evidence. WSL does not establish native Windows support. | [01: U00 baseline and feasibility](01-cli-contracts-engines-outputs.md) |
| U00 | Tests on explicitly defined Debian/Ubuntu releases and a documented OS/architecture/backend matrix. | [01: U00](01-cli-contracts-engines-outputs.md), [03: acceptance matrix](03-cli-batches-validation-release-0.2.0.md) |
| U00 | Clean-cache startup, all model downloads, readiness timing, and RAM limits. Warm-cache runs are not cold-install evidence. | [02: installation and runtime validation](02-cli-diagnostics-runtime-installation.md) |
| U00 | Broader content review covering figures, tables, equations, references/links, and scans, with engine-specific expectations. | [01: engine validation](01-cli-contracts-engines-outputs.md), [03: corpus](03-cli-batches-validation-release-0.2.0.md) |
| U00 | Complete inference-service startup and failure-path evidence: bounded startup, failed downloads/readiness, process cleanup, and recovery. | [02: U04–U05](02-cli-diagnostics-runtime-installation.md) |
| U01 | Interruption must produce a terminal `cancelled` job result and `run_finished`, with cleanup. This is not guaranteed by the current signal-handler path. | [01: protocol contract](01-cli-contracts-engines-outputs.md), [02: supervisor](02-cli-diagnostics-runtime-installation.md) |
| U01 / U02 dependency | Collision-safe naming and publication remain incomplete; current output may overwrite existing files. Implement numbered outputs and transactional publication in U02. | [01: U02 outputs](01-cli-contracts-engines-outputs.md) |
| U01 | Complete error events for failures before document processing, including app-home and runtime setup. Consumers must receive an explicit failure instead of only a crash or stderr. | [01: events](01-cli-contracts-engines-outputs.md), [03: exit/error semantics](03-cli-batches-validation-release-0.2.0.md) |
| U01 / later integration | `health --json` and `--control-stdin` are planned but not implemented. Their absence must remain visible in the public-contract status. | [02: health](02-cli-diagnostics-runtime-installation.md), [03: CLI surface](03-cli-batches-validation-release-0.2.0.md) |
| U01 | Broader output review beyond byte-for-byte Marker parity on the two test PDFs. | [01: U01 acceptance](01-cli-contracts-engines-outputs.md) |
| U02 onward | All remaining engine/output, diagnostics/runtime, installation, CLI completion, validation, and release work remains open unless separately evidenced. No release-readiness claim. | Plans 01–03; UI remains a later `0.3.0` delivery. |

Runtime logs, models, and conversion outputs referenced under `/tmp` or user caches are machine-local and are not backed up by Git. Their commands, package/model identities, hashes, results, and limits are recorded in the evidence document. If those local artifacts are unavailable on resume, regenerate them or mark that evidence unavailable; do not assume a successful rerun.

The work is divided into five plans to execute in order. Each identifies files, contracts, work units, tests, evidence, and completion criteria. User requirements are fixed here; the technical choices proposed within each stage may be adjusted based on evidence without changing those requirements.

## Implementation order

| Order | Plan | Units | Branch and outcome |
|---|---|---|---|
| 1 | [CLI contracts and engines](01-cli-contracts-engines-outputs.md) | U00–U02 | `refactor/0_2_0_sami_cli`: feasibility, public contract, preserving Marker, fast engine, and outputs. |
| 2 | [Diagnostics, runtimes, and installation](02-cli-diagnostics-runtime-installation.md) | U03–U05 | Same CLI branch: persisted diagnostics, fast health check, CPU fallback, and complete bootstrap. |
| 3 | [Batches, progress, validation, and CLI release](03-cli-batches-validation-release-0.2.0.md) | U06–U07 | Complete CLI, merge into `main`, and publish **`v0.2.0`**. |
| 4 | [Electron application](04-ui-electron-application-0.3.0.md) | U08–U09 | `feat/0_3_0_sami_ui` starts from `main` with CLI `0.2.4` published. Import the assets from `sami-assets.tar.gz` and remove the archive after verifying the import. Then build over protocol v1. |
| 5 | [UI deployment and release](05-ui-deployment-release-0.3.0.md) | U10–U11 | Validate the prebuilt Windows installer and Linux AppImage with the pinned CLI, then publish **`v0.3.0`** from `main`. |

The CLI release does not wait for the UI. Do not create the UI branch during initial CLI implementation. Never move tags to add components later.

## Requirements the implementer must preserve

| Area | User decision |
|---|---|
| Conversion | Preserve SAMI/Marker's Markdown conversion logic; use the fast engine only for `fast` mode. |
| Modes | `fast`, **`balanced` by default**, `quality`. Working technical mapping: the fast engine, Marker `fast`, and Marker `balanced`, respectively. Validate in U00/U01. |
| Fast engine configuration | Use its actual invocation: `quality="high", ocr=False, images=False`. Preserve text, tables, heuristic layout, markers, and existing checks without adding heavy models. |
| References | Always retain bibliography text and recoverable links inside the `.md`. No `.bib` or dependency on external bibliography artifacts; do not invent URLs. |
| Existing outputs | Create a new numbered output, preserving previous versions. |
| Execution | Everything local and keyless; after installation, all three modes work without further downloads. |
| Hardware | Prioritize CPU and VRAM; also inspect RAM, OS, architecture, drivers, and relevant components. |
| Diagnostics | Deep checks during installation. Persist positive and negative results; use a quick check when running CLI/UI. |
| Installation | Prepare all three modes, models, and the CPU path. Automatically prepare private dependencies; manage system drivers in an explicit step. |
| GPU failure | Warn and continue on CPU in the same mode, without prompting or blocking due to acceleration. |
| Desktop platforms | Native Windows 11 and the AppImage on Arch Linux and a named Debian-based baseline. macOS is secondary. |
| Inputs and progress | Stage multiple PDFs or folders via drag and drop or the system picker. Start with the Convert button. Show activity, current stage, time in stage, and real counters when available until the operation finishes. |
| CLI first | It must be complete, tested, installable, and published before building the UI. |
| UI | Electron, JavaScript, and HTML/CSS use CLI commands and events. Show **SAMI — Smart Automated Markdown Interpreter** with a muted purple accent, English and Spanish, and light and dark appearance. |
| UI dependencies | Prefer maintained libraries that solve the task and work in the packaged Windows and Linux apps. Use built-in APIs for straightforward operations. |
| Windows desktop integration | Per-user installer with registration in Installed apps and shortcuts in Start and on the desktop. |
| Linux desktop integration | Prebuilt AppImage with an icon and per-user application menu entry installed by the bootstrap. |
| Distribution | Build in CI for native Windows and Linux. The installer uses published UI packages and the exact compatible CLI. Node.js, npm, and pnpm are build-time tools. |
| Graphical UX | Inbound/outbound drag and drop, PDF/Markdown viewers, paths, open-folder action, and workspace/output selection. |

## How to execute these plans once authorized

1. Read this index and plan 01. U00 is a feasibility check, not permission to change the engine if a dependency fails.
2. Complete each unit with code, tests, and documentation for the same behavior. Record actual results and limits; a checked box is not evidence.
3. Keep fast tests independent of models/network; run engine and installation tests separately when the unit requires them.
4. Do not move to the next plan with an incomplete contract that would force the UI to duplicate rules.
5. Each stage's release requires a SHA merged into `main`, tested artifacts, and consistent versions per component.

The plans name modules to clarify responsibilities; modules may be combined if that simplifies the code. Do not create empty layers, production mocks, an HTTP server, a permanent daemon, or an embedded terminal merely to reproduce the document structure.

The change has a high risk of exceeding 400 lines per PR. Preserve the two requested branches and reviewable units; document size, strategy, and justification when preparing PRs. Do not reduce line counts by deleting comments or present several commits as several small PRs.

## Evidence record per unit

Use this template to track implementation; do not fill it with assumed results:

| Field | Contents |
|---|---|
| Identity | Unit, branch, commit, and comparison baseline. |
| Change | Completed behavior and specific files. |
| Focused tests | Exact command, output/exit code, and environment. |
| Runtime verification | Scenario/artifact/result; or `N/A` with a reason if no execution boundary is crossed. |
| Validated scope | OS, architecture, CPU/GPU, runtime/model, and versions where relevant. |
| Open risks | Outstanding failures and their actual effect on delivery. |
| Rollback | Unit that can be reverted without deleting user documents or results. |

## Technical details still open

- Exact Debian/Ubuntu versions, architectures, and GPU/backend combinations: U00 must verify these before committing to support. Initial proposal: x86_64; this does not imply support for every Debian derivative/version.
- Locks, packages, and CPU/GPU backend: resolve and pin in U00/U04. Having CUDA/ROCm in PyTorch does not prove the VLM uses the GPU. **Decided in [06 — engine backend and GPU policy](06-engine-backend-and-gpu-policy.md):** the only heavy-inference backend is local `llama.cpp` (GGUF); Docker/vllm is prohibited; GPU is a VRAM-scaled `-ngl` offload for the `quality` VLM only; hardware never switches the public mode.
- The transport, event names, and commands in plan 01 are the proposed technical specification. Freeze them in tests before developing Electron.
- Additional advanced OCR, image, page, and concurrency flags remain proposed extensions, with explicit scope in plan 03. They must not change the chosen fast profile or delay agreed requirements without a documented reason.

## Working references

- [Complete previous design, retained as a historical reference](00-previous-design-reference.md). Its old sections do not override the active plans.
- The reference extraction code (removed from the repository).
- [06 — engine backend and GPU policy](06-engine-backend-and-gpu-policy.md): authorized decision on llama.cpp backend, per-mode device matrix, VRAM offload ladder, and Windows+Linux parity.
- [Current SAMI entry point](../../../sami/cli.py), [metadata](../../../pyproject.toml), and [repository guide](../../../CLAUDE.md).

This planning split only creates/modifies documents in this folder. It does not change the actual version, create branches, or execute installation/release steps.
