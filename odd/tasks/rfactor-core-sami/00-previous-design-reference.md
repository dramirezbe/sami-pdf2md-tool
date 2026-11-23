# Historical reference — superseded by the staged plans

This document retains the complete previous design, translated into English, for reference. The current entry point is [the plan index](2026-11-18_10-31-38_sami-refactor-plan.md) and its five numbered plans. If they differ, follow the index and active plans; do not implement from this historical reference.

---

# SAMI refactor: hardware, three modes, CLI, and cross-platform installation

Opened: **2026-11-18 10:31:38**, America/Bogota (UTC−05:00).
Last design update: **2026-11-18 11:29:26**, America/Bogota (UTC−05:00).
Author: Codex, based on user requirements and decisions.
Status: **analysis for discussion; implementation not authorized**.
Reviewed baseline: commit `6452f12`, local SAMI code, and the reference extraction code.

The proposal preserves SAMI's Markdown conversion logic and adds a fast engine. The refactor separates machine diagnostics, dependency preparation, resource selection, conversion, and presentation. The first delivery covers core, CLI, and installers, prioritizing Windows 11 and Debian-based Linux; macOS is secondary. UI is a later independent delivery communicating exclusively through CLI commands/events.

Quick reading: section 7.5 collects intended final CLI features; section 8 defines CLI-first/UI-later deployment; section 9 retains the Electron stack and graphical requirements. Section 12 consolidates settled daily-use decisions. Section 13 lists branches/files; section 14 publishes CLI `0.2.0` after its merge into `main`, followed by UI `0.3.0` in section 15. All scope describes future design, not implemented features.

This task produces only this document. No components have been installed, drivers changed, conversions run, or application code modified. Commands, modules, and behaviors below are proposals.

## 1. Confirmed decisions and open details

| Topic | Status and scope |
|---|---|
| Current SAMI conversion | **Preserve** its Marker-based Markdown conversion logic. Hardware adaptation must not replace it with fast-engine heuristics. |
| Fast engine | Used only for `fast` mode; it does not replace SAMI's higher-quality modes. |
| Public modes | `fast`, `balanced`, `quality`. The user corrected the middle name. Section 5 proposes the last two modes' Marker mapping. |
| Default mode | **`balanced`**, confirmed by the user. |
| `fast` behavior | Use the effective fast-engine batch configuration: `quality="high"`, `ocr=False`, `images=False`; retain lightweight text/table extraction without added heavy work. |
| References | **Always retain** bibliography and links inside Markdown. Do not remove them or export them as external bibliography artifacts. |
| Existing files | Create a new numbered output by default, retaining previous versions. |
| Persisted diagnostics | Full diagnostics during installation; save and reuse results. Normal use performs only a quick compatibility health check. |
| Execution and privacy | Everything local, without API keys or external conversion services, including `quality`. Installation/model downloads do not mean uploading documents. |
| Automatic preparation | Prepare all three modes and CPU paths during installation, with compatible GPU where applicable. Do not ask users to install modes/models later. System drivers use an explicit step. |
| GPU failure | Warn and automatically continue on CPU in the same mode; do not block conversion or request confirmation due to acceleration failure. |
| Platforms | Confirmed priority: **Windows 11 and Debian-based Linux**. macOS is secondary and does not gate the first delivery. Exact distribution versions/architectures remain to be defined. |
| CLI inputs | One or multiple files, PDF folders, and combinations; per-file and per-batch progress. |
| UI | Second delivery. Independent CLI-dependent application, without reusing/importing conversion code. Prioritize usefulness and development ease; package size/UI performance are not priorities. Recommended stack: Electron with JavaScript, HTML, CSS. |
| Deployment order | Install, validate, and make CLI independently usable before UI. Graphical installation depends on CLI health; the resulting `.exe` opens by double-click without manual preparation. |
| Windows UI integration | Deployment creates desktop/Start menu shortcuts and makes launchers available in `PATH`. Application ready without manual configuration. |
| Work restriction | Discuss decisions before implementation. |
| Development branches | `refactor/0_2_0_sami_cli` for core/CLI/installers; `feat/0_3_0_sami_ui` for Electron and its CLI-dependent deployment. |
| Target releases | **CLI `0.2.0`**, tag `v0.2.0`, after its merge into `main`; **UI `0.3.0`**, tag `v0.3.0`, after its later merge. CLI publication does not wait for UI. |

Default profile, fast-engine behavior, references, existing outputs, complete preparation, and CPU fallback are settled. Remaining capability, flag, and version-matrix details are listed at the end.

## 2. Verified repository starting point

| Current part | Observed behavior | Refactor consequence |
|---|---|---|
| [sami/cli.py](../../../sami/cli.py) | Integrates Marker, reproduces its stages in `VerboseConverter`, writes Markdown/figures. | Preserve pipeline/result; isolate integration without rewriting conversion rules. |
| Current modes | Exposes `fast` and `balanced`; without a flag, delegates some decisions to Marker. | New names need explicit migration; old `fast` and new `fast` use different engines. |
| Hardware | Tunes CPU threads; queries CUDA VRAM and uses an 8 GiB threshold to select `fast` where applicable. | Need PyTorch-independent inventory, available memory, AMD, and inference-server backend distinction. |
| Preparation | Downloads `llama-server`; creates directories before parsing arguments. | `--help`, `--version`, and read-only diagnostics must work without downloads/models. |
| Process lifecycle | Uses POSIX signals and child tracking. | Need Windows supervisor implementation; retain cleanup of owned processes. |
| Inputs/progress | Accepts multiple explicit files; prints stages, times, batch index. | Does not currently accept folders or implement two progress bars. Those are new work. |
| Output | Per-PDF subdirectory except `--flat`; removes references by default; publishes individual moves from staging. | Change to permanent references/links and numbered outputs; strengthen publication while retaining Marker conversion. |
| [install.sh](../../../install.sh), [setup.sh](../../../setup.sh) | Bash; uv/micromamba installation and NVIDIA Docker preparation in some Linux environments. | Not Windows installers; must not assume `apt` for all Linux. |
| [pyproject.toml](../../../pyproject.toml) | Marker mandatory; Python `>=3.11,<3.14`. | Separating fast base/heavy components requires packaging changes, not merely flags. |
| Reference extraction code (removed from the repository) | PyMuPDF, pdfplumber, optional Tesseract, layout heuristics, manifest, auditing. | Extract only fast engine/useful diagnostic concepts; do not import globally executing cells. |

The reference extraction code formerly lived in `refactor-core-sami/`. This analysis is stored in `rfactor-core-sami/`, honoring the requested task path.

## 3. Machine diagnostics: what to measure and when

Full inventory runs during installation, precedes runtime selection, and works without PyTorch. Save results for later executions. This task does not audit the current machine; it specifies SAMI behavior on each installation device.

| Area | Required data | Use |
|---|---|---|
| OS/architecture | Windows/Linux/macOS, version, distribution, kernel, x86_64/arm64, WSL/container. | Select compatible artifacts/recipes. Treat WSL as Linux with its own capabilities. |
| CPU | Architecture, physical/logical cores, affinity, quotas where available. | Size processes/threads within actual allocations. |
| RAM | Total/free, shared/unified memory. | Bound rasterization, concurrency, and models. |
| GPU | All GPUs, vendor, identifier, architecture, driver, queryable total/free VRAM. | Distinguish physical presence from effective compatibility and select device. |
| Components | Runtimes, libraries, inference server, Tesseract/languages, models, available managers. | Reuse compatible components, avoid repeated downloads. |
| Quality of life | Free space, write permissions, relevant power/network availability. | Detect preparation/output problems before conversion. |

Record unqueryable data as `unknown`, not as no GPU or confirmed compatibility. Avoid collecting unrelated personal paths or full environment variables.

Separate full installation diagnostics from normal health checks. Installation diagnostics include inventory, runtime validation, and a minimal actual-engine test. Seeing a GPU or running a PyTorch operation alone does not prove accelerated VLM serving.

### 3.1 Persisted compatibility profile

Proposed format: versioned local JSON within private SAMI state, honoring `SAMI_HOME`. Save diagnostic date, schema, OS/architecture, GPU identifiers, driver, runtime/engine versions, validated models, effective backend/device, tests, incompatibility reasons. Always record validated CPU paths for all three modes: required acceleration-failure fallback.

Persist positive and negative results: unsupported GPU or missing driver must not trigger expensive analysis every invocation. Associate results with component fingerprints to detect changes. Save atomically and coordinate with installer; never expose a partially prepared environment as ready.

Do not expire profiles merely with time or repeat full diagnostics per file/batch/CLI startup. Invalidate only affected capabilities when change evidence exists. Engine/model updates validate their components during installation and update the profile.

### 3.2 Fast health check before conversion

Before a batch, read profile and check schema, active environment, and required components for the chosen mode. Compare lightweight component/driver fingerprints where available; do not rehash all models or scan installed packages. Check once per invocation/batch, not per PDF.

Normal path does not import PyTorch/Marker, load models, start inference servers, access network, or install anything. External OS queries, if needed, have timeouts and a bounded global budget. Initial measurable target: under one second of added cost on prepared machines, avoiding even this check for `--help`/`--version`.

Free RAM/VRAM can change without compatibility changing. Query lightly before resource reservations with time limits; use conservative budgets and report uncertainty when unavailable. Normal model loading remains necessary at job preparation, but does not repeat installation diagnostics.

If GPU capabilities change or checks fail, warn and continue through the prepared CPU path, retaining the requested profile without confirmation. Do not start deep diagnostics on CLI opening or downgrade `quality` to `fast`. Missing/corrupt general records are installation-integrity issues: maintain a recoverable CPU-path record; missing GPU evidence must not stop a valid CPU conversion.

Quick checks cannot guarantee a backend never fails later. On actual initialization incompatibility, record failure/invalidate that capability; do not repeat expensive attempts with the same fingerprint every execution. Deep analysis belongs to explicit installation, component update, or repair flows.

## 4. Acceleration and automatic preparation

### 4.1 Compute backend and inference server are separate decisions

Diagnostics distinguish detected hardware, usable driver, available runtime, validated engine. For VLM profiles, also record the model-serving process and its device.

PyTorch ROCm reuses interfaces under `torch.cuda`; that name alone does not identify NVIDIA. Distinguish HIP from CUDA. See [PyTorch HIP semantics](https://docs.pytorch.org/docs/2.15/notes/hip.html).

| Environment | Proposed target | Readiness condition |
|---|---|---|
| Windows/Linux + NVIDIA | CUDA when supported. | Verified driver, runtime, binaries, actual engine execution. |
| Windows/Linux + AMD | ROCm/HIP on explicitly supported combinations. | Validate GPU, OS, driver, framework, inference backend. |
| Compatible macOS | Metal/MPS and/or server Metal backend. | Actual-backend test and unified-memory budget. |
| No usable acceleration | CPU. | CPU dependencies prepared and engine execution within limits. |

AMD's hardware/environment matrix means support cannot be inferred for every Radeon or Windows/Linux version. Framework support does not demonstrate Marker/Surya support. See [official ROCm matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html). macOS must account for [MPS](https://docs.pytorch.org/docs/2.15/notes/mps.html) and server-specific backends.

Marker 2.0 documents a separate VLM server: vLLM/Docker on NVIDIA, llama.cpp elsewhere. Installing a CUDA/ROCm PyTorch wheel alone does not accelerate VLM serving. AMD/native-Windows backend viability needs early validation, not assumed capability. See [Marker 2.0 usage/inference](https://github.com/datalab-to/marker/blob/v2.0.0/README.md#usage).

### 4.2 Proposed preparation during installation

1. Inventory CPU, GPU, OS, existing components, free space.
2. Resolve versioned compatible combinations per requested engine.
3. Reuse system components only after checking version and operation.
4. Prepare missing components in a private SAMI environment through supervised background work.
5. Validate before activation; do not modify an environment currently converting documents.
6. If a driver is needed, explain the explicit step and retain ready CPU execution without blocking conversion due to missing acceleration.
7. Persist results and show readiness, ongoing preparation, and limitation reasons.

This complete flow belongs to installer and explicit component installation/repair. Normal CLI runs reuse the profile and only perform section 3.2 health checks. If background installation continues, CLI reads its persisted status without starting another diagnosis.

Suggested preparation states: `not_checked`, `preparing`, `ready`, `needs_driver`, `unsupported`, `failed`. Each includes an actionable reason.

"Background" means tracked work with logs/queryable results, not an abandoned process. If a requested mode depends on an ongoing download, show preparation and wait or allow cancellation. Never switch batch engines mid-run when installation finishes.

Private preparation must not require changing global Python, restarting Docker, changing kernel modules, or automatically updating drivers. Such operations belong to the explicitly agreed driver step. If reboot is required, distinguish installed components from actually usable acceleration.

Recommendation: closed recipes per OS/architecture/backend, pinned dependencies/models, verifiable downloads, and new-environment activation after testing. Lock incompatible concurrent preparations and retain previous environment on failure. Do not automatically compile large dependencies from source.

### 4.3 Meaning of cross-platform support

Separate commitments: SAMI installs/converts on the OS; a particular GPU accelerates a particular engine. The first cannot depend on the second.

Confirmed priority: **native Windows 11 and Debian-based Linux**. Initial architecture proposal: x86_64 for both, with Debian/Ubuntu/derivative versions defined through dependency availability and tests. Debian ancestry does not guarantee identical binaries/drivers across versions. WSL success alone does not establish native Windows support.

macOS remains secondary: preserve adapters/packaging possibilities without blocking first delivery over Intel/Apple Silicon, minimum versions, or Apple acceleration. Linux arm64/Windows arm64 do not automatically enter the stable matrix.

On priority platforms, all three profiles need tested local CPU paths prepared at installation. This is a fallback acceptance criterion, not a capability demonstrated by this analysis. Verify models, inference server, process cleanup, artifacts; GPU improves that baseline. Do not promise CPU/GPU speed parity.

## 5. Three modes preserving SAMI conversion

| Public mode | Proposed engine | Priority and behavior |
|---|---|---|
| `fast` | The fast engine's batch extraction: PyMuPDF/pdfplumber with internal `high`, OCR/images off. | Retain fast text/table path without Marker, PyTorch, Tesseract, VLM. |
| `balanced` | Current SAMI pipeline, Marker configured `fast`. | Retain Marker structure handling at lower cost than its `balanced` mode. |
| `quality` | Current SAMI pipeline, Marker configured `balanced`. | Prioritize reconstruction/recognition; always local and keyless. |

The fast/Marker separation follows explicit user instruction. The two Marker-profile mappings are a proposal to validate on representative documents. Names do not promise higher quality on every page.

Do not apply fast-engine normalization, paragraph reconstruction, or heading heuristics to Marker Markdown. Preserve content, figures, rendering logic; refactor interfaces/management around the engine. Validation improvements may produce separate reports without rewriting output.

Marker 2.0 differentiates profiles and OCR/VLM usage; copying fast-engine names is insufficient. Bind exact settings to the validated version. See [Marker 2.0 mode configuration](https://github.com/datalab-to/marker/blob/v2.0.0/README.md#usage).

### 5.1 Profile and resource decisions

| Decision | Fixed behavior or technical criterion |
|---|---|
| Default profile | **`balanced`**, confirmed. Prepared during installation with the other modes. |
| GPU failure/insufficient VRAM | Warn and continue automatically on CPU in the same mode, without dialog/acceleration-related blocking. Prepare/test fallback at installation. |
| `fast` scans | **No automatic OCR**, matching the effective fast-engine configuration. Record unextractable page/partial status; do not load a heavy engine or silently change mode. |
| Per-page quality | Evaluate illegible-text signals, table structure, reading order; not text quantity alone. |
| Resources | Separate quality mode from device/concurrency. Current 8 GiB threshold is not universal across models. |

Memory limits consider model, precision/quantization, resolution, context, batch, free memory. On Apple Silicon, do not count RAM/GPU memory as independent pools.

GPU failure during conversion discards incomplete attempt staging and retries that document on CPU. Disable failed backend for the rest of the batch; record reason to avoid repeated expensive attempts under identical conditions. Distinguish persistent incompatibility from transient memory pressure; recovery must not bother the user each invocation. Fallback warnings alone do not mean failure if CPU conversion succeeds.

### 5.2 What to extract and review from the reference extraction code

Take fast extraction, tables, heuristic ordering, gap recording. Separate auditing from engine to prevent conversions/sampling on import.

Speed decisions follow the **actual invocation** in the reference extraction code (removed from the repository), not its `fast` preset name: the batch uses `Options(quality="high", ocr=False, images=False, overwrite=True)`. Internal `fast` disables features the batch uses. Thus public SAMI `fast` preserves table/heading detection, reading order, markers, `pipe` tables, and `run` consistency checks with OCR/images off. Replace original overwrite policy with numbered outputs because the user chose to retain earlier conversions.

Do not automatically execute the separate random-audit cell or add OCR/VLM/layout models here. Preserving bibliography links needs lightweight recovery of PDF links; the reference code lacks explicit handling of all link annotations. Measure adaptation/refactor cost versus the original batch on the same machine/corpus. The fast engine's speed is the acceptance objective; no measurement yet establishes identical speed across machines.

Do not copy reactive OCR rescue unreviewed: it compares output against the OCR text it used to construct that output and may suggest improvement without independent evidence. Cell-token comparisons do not validate row/column positions; rescue markers do not match the auditor pattern. Classify PDF origin before OCR rather than calling newly recognized text native.

The user's experience with the reference code's speed motivates this design; no local benchmark yet compares both engines under equivalent conditions.

## 6. CLI core and component boundaries

Proposed responsibilities, not implemented file structure:

| Component | Responsibility |
|---|---|
| `hardware` | Full installation diagnostics, persisted compatibility profile, fast health check, independent of heavy models. |
| `runtime` | Resolve/prepare/verify dependencies/models during installation; manage backends/owned processes in conversion without repeating diagnosis. |
| `engines` | Fast and SAMI/Marker adapters without terminal/window logic. |
| `jobs` | Discover inputs, plan batches, allocate resources, cancel, continue after failures. |
| `outputs` | Paths, collisions, resources, staging, result publication. |
| `validation` | Diagnostics/quality status with explicit verification scope. |
| `events` | Structured progress/results for CLI/future UI. |
| `cli` / future `ui` | CLI is the UI's only core entry point. Graphical app executes commands/consumes public job protocol; no Python imports or duplicated conversion rules. |

Define conversion requests with inputs, mode, options, output policy, device. Return files, status, warnings, metrics, effective engine/device. Identify jobs/pages so events can be correlated without parsing printed messages.

Heavy engines should run in supervised processes for cancellation, environment isolation, memory recovery. Use versioned events, such as JSON Lines over local pipes; no HTTP service/permanent daemon needed. Transport choice remains open in this historical design.

Cleanup terminates only processes SAMI created for the job. Windows needs process-tree management; POSIX uses appropriate groups/signals. Do not find/kill global processes merely because their names contain `llama`.

## 7. CLI and file behavior

### 7.1 Selection and options

Preserve direct `sami file.pdf`, multiple files, `-o/--output`, `--mode`, `--flat`, `-q/--quiet`, help, documented exit codes. Reference preservation becomes permanent: accept `--no-strip-refs` as a compatibility no-op; do not expose a new reference-deletion flag or call `strip_references` in conversion.

Future interface examples, not commands available yet:

```text
sami document.pdf --mode fast
sami one.pdf two.pdf --mode balanced
sami pdf-folder/ --recursive --mode quality
sami one.pdf pdf-folder/ --output results/
sami health --json
sami doctor
sami setup
```

Additional proposal: expose device, concurrency, OCR/languages, images, page markers, selection/page limits, existing-file policy. Clearly reject unsupported options instead of accepting/ignoring them. Advanced Marker-specific options may use separate validated configuration.

Not all these options exist in SAMI today. Evaluate the fast engine's controls as extensions while distinguishing existing compatibility.

Both existing mode names change meaning in the proposed mapping: old SAMI `--mode fast` becomes new `balanced`; old `--mode balanced` becomes new `quality`. New `fast` uses the extracted fast engine. `balanced` cannot also alias `quality` because it becomes a public profile itself. Document/test migration, including saved defaults/user scripts.

### 7.2 Folders and batches

Flag-controlled recursion, deterministic order, identity/normalized-path deduplication. Resolve links/case differences according to OS; avoid cycles. Do not traverse output directories automatically or process a PDF twice when supplied explicitly and found in a folder.

A damaged PDF must not abort the batch. Record encrypted, unreadable, failed, partial, skipped inputs with explanations. Preserve originals. Batch progress counts unique jobs, not input arguments.

### 7.3 Workspace and output

Proposal: `--output` determines output; otherwise each PDF uses its source directory, as current SAMI. Default per-document subdirectory with Markdown/resources; `--flat` keeps its meaning.

For PDFs from different folders, retain per-input behavior unless a common destination is chosen. Never derive all outputs from the first PDF's directory. Future UI shows source/effective destination before starting.

Separate chosen document/result workspace from private caches/models/logs. Use suitable locations per OS, retaining `SAMI_HOME` override.

Confirmed: existing outputs cause a new numbered output, retaining both versions. Apply matching output identity to Markdown/resources to avoid same-name collisions across source directories, especially shared output or `--flat`. Alternative policies, if exposed, are explicit and never replace this default.

Publication coordinates Markdown/resources: failed conversion must not damage prior output. Mechanism depends on replacing complete directories versus publishing immutable resources followed by Markdown.

Bibliography/reference links remain in the same `.md`, without `.bib`, bibliography JSON, or another external artifact needed to read them. Operational interpretation: retain text and inline Markdown links to recoverable PDF destinations; keep internal links using document anchors where possible. Do not invent URLs or resolve references through external services. Annotation recovery belongs in both engines' test cases.

### 7.4 Two progress levels

Show current-file and batch progress, including name, stage, completed/total files. Separate model preparation from conversion to explain first-use time.

Count real pages/units where exposed. If Marker stages lack measurable progress, display indeterminate activity/stage, not invented percentages. Do not rewrite conversion merely to simulate a bar.

Batch bars may represent completed jobs/total, not remaining-time estimates when document sizes differ. Counters distinguish success, partial, failure, cancellation. Concurrent jobs, if used, each need identifiable progress.

Quiet, non-TTY, structured output need appropriate presentation. Future UI consumes the same events, not parsed text logs.

### 7.5 Intended final CLI functionality

Consolidated first-delivery scope, updated with user decisions. Proposed flags/technical details are distinguished afterward; syntax examples alone do not confirm decisions.

| Feature | Expected result |
|---|---|
| Independent use | Install/use SAMI fully in terminal before UI exists, without depending on UI. |
| Inputs | One/multiple PDFs, a folder, or combinations; optional recursion, deterministic order, deduplication. |
| Three modes | `fast` runs the fast engine with OCR/images off; **`balanced` default** and `quality` retain SAMI/Marker. Proposed internal mapping: Marker `fast`/`balanced`, respectively. |
| Output content | Markdown text plus structure/tables/equations/figures according to engine/options. Retain Marker behavior; state fast-engine limits. |
| Local processing | Keyless/no external conversion; installation prepares all modes for later offline operation. |
| Installation diagnostics | Detect CPU/RAM/GPU/VRAM/OS/architecture/drivers/components; validate engines, persist positive/negative results. |
| Normal health | Quick pre-batch check without models/downloads/deep analysis; detect changes and repair requirements. |
| CPU/GPU resources | Validated CUDA/ROCm on priority platforms; GPU failure warns/continues CPU in same mode. Metal remains secondary macOS scope. |
| Preparation/maintenance | Install three modes/models/CPU fallback; no later dependency-completion prompts in normal use. Query status, update/repair recoverably. Explicit driver step. |
| Progress | Per-file and batch-count bars, stages, times; indeterminate activity without actual percentages. |
| Output directory | Select destination or use each PDF's directory, per-document folder and `--flat`; new numbered output when prior output exists. |
| References/current controls | Always preserve bibliography/embedded links; compatibility no-op `--no-strip-refs`, quiet, help, exit codes; document mode migration. |
| Errors/cancellation | Continue past individual failure; explain errors/partials; cancel/clean owned processes; preserve original PDFs/prior valid results. |
| Results/diagnostics | Per-document/batch summary with status, paths, warnings, effective engine/device; explicit-scope consistency reports, not false fidelity certification. |
| Automation/future UI | Health JSON, progress/results JSONL, versioned cancellation control; separate logs for scripts/Electron. |
| Cross-platform installation | Windows 11 `irm`, Debian-based Linux `curl`, command on `PATH`, update/uninstall. Secondary macOS. |

Proposed public extensions: device, concurrency, OCR/languages, images, page markers, ranges/limits. Expose supported options or fail clearly; do not promise engine capability parity. Define exact flags/capabilities during final design.

Proposed management: `sami health` quick human/JSON check; `sami doctor` explains persisted diagnostics without deep tests; `sami setup` explicitly enters installation/preparation/repair. Update/uninstall share installer component records; additional command names remain unfixed.

Settled daily behavior: default `balanced`, the fast engine's batch configuration without OCR/images, references/links always in Markdown, numbered outputs, three modes prepared at installation, warning/automatic CPU fallback. Advertise GPU support only for verified combinations, not every vendor card.

## 8. Installers and distribution

Priority first delivery: Bash bootstrap with `curl` for Debian-based Linux, PowerShell with `irm` for Windows 11. Secondary macOS. Define public URLs after artifacts exist; do not publish instructions for nonexistent components.

Proposal: per-user managed Python/private environments, reusing compatible components. uv can obtain Python without manual preparation; see [uv Python management](https://docs.astral.sh/uv/guides/install-python/). Compare with a packaged CLI; the user has not selected a CLI binary format in this historical design.

Install fast base and **both Marker profiles**, including all models/components and CPU fallback, in initial installation. Prepare compatible acceleration and persist complete diagnostics. Users do not select/install modes later. First normal use and help must not trigger deep analysis/model downloads.

Separate core, fast engine, Marker engine, runtimes, models. A mandatory heavy Marker dependency in the base would prevent lightweight `fast` installation. Python extras alone do not resolve every CUDA/ROCm variant: pin environments per platform/runtime.

Pin releases/artifacts/tested combinations instead of resolving `latest` every time. Recoverable update, repair, uninstall share component records. Offline operation follows complete preparation; interrupted network setup preserves recoverable state without falsely announcing completion.

Build/verify artifacts per supported OS/architecture. Cross-platform release tests clean installation, update, uninstall, local execution, cancellation; GPU support also needs real hardware. Installers do not replace these tests.

Windows PowerShell bootstrap and future downloadable UI installer converge on one installation/component record. First CLI delivery configures launcher/`PATH`; later UI adds desktop/Start shortcuts and executable from section 9.1. Rerunning must not create a second independent installation or duplicate shortcuts.

### 8.1 One installer, two ordered stages

Separate product delivery timing from installation steps. Publish complete independent CLI first, UI later. Once both exist, a single `irm` bootstrap chains both stages without two user commands. CLI-only installation and later UI addition remain available.

| Step | Windows deployment action | Result required to continue |
|---|---|---|
| 1. Resolve installation | Detect owned SAMI installation and compatible published versions. | Explicit plan to install/reuse/update CLI before adding UI. |
| 2. Install CLI/core | Deep diagnostics for new installation; prepare three modes/CPU fallback/compatible GPU, persist compatibility, configure launcher/`PATH`. | Independent CLI, all modes prepared, complete persistent record. |
| 3. Validate CLI | Installation tests and structured health; existing installs start with quick health, repairing explicitly if needed. | Executable core, compatible version/protocol, three ready profiles; GPU failure warns/uses CPU. |
| 4. Install UI | Deploy graphical executable/presentation dependencies over core. | UI linked to validated CLI without duplicate engines/models/diagnostics. |
| 5. Integrate/check | Desktop/Start shortcuts, target checks, UI–CLI communication and startup. | Completed installation; `.exe`/shortcuts work by double-click. |

Wait for all three modes/CPU fallback before announcing readiness. Background preparation does not mean leaving dependencies/models for first double-click or an unused mode. Failed GPU setup warns and completes with prepared CPU, without acceleration-related blocking.

Before UI publication, bootstrap installs/validates CLI and stops; no shortcuts to nonexistent graphical executables. Later complete installation includes both stages; CLI-only remains available.

If CLI fails, do not continue graphical installation or announce complete success. If UI fails after CLI validation, retain operational CLI and retry only graphical stage. Missing drivers retain explicit handling; a valid CPU path satisfies health without silently lowering quality.

### 8.2 Health contract between installer, CLI, UI

Future command proposal: `sami health --json`, versioned structured output/documented exit. Quick persisted-state/lightweight check; never starts deep diagnostics/downloads/installation. Installer performs deep tests separately, then queries this contract.

Identify installation, CLI/core version, job-protocol version, compatibility-profile validity, preparation state, three modes, concrete repair reasons. Distinguish core failure from unusable GPU: validated CPU with warning continues/opens UI. Complete installations leave no profiles pending download.

UI declares supported protocol/core versions. Deployment verifies before installation and records the component relationship. Use registered absolute private CLI launcher path, independent of Explorer `PATH` refresh, open terminals, other `sami` installations earlier in environment.

Communication proposal: local CLI/core process, structured arguments, JSON Lines over pipes, no visible console. UI consumes protocol results/events, not conversion logic/text logs/shell strings. Graphical executable packages independently without duplicating heavy conversion environments.

UI updates first check installed-core health/compatibility. CLI updates retain a compatible pair or update both recoverably. UI-only uninstall retains CLI/models/config; removing a core depended on by UI is a coordinated, explained operation.

### 8.3 First double-click and subsequent openings

UI locates registered installation, queries quick health once, opens with prepared engines. No Python activation, command entry, or repeated GPU preparation. Deep diagnosis remains installation work; loading an engine at conversion start is normal job work.

If drivers change/components disappear after installation, show graphical explanation and explicit repair action without silently closing or opening a console. Offer capabilities still validated. Recovery must not turn every opening into automatic reinstallation.

## 9. Desktop UI packaged per OS: later scope

Second-delivery requirements retained: drag files/folders from Explorer, Finder, Linux managers; drag results to other applications; embedded PDF/Markdown viewers; visible paths; open-folder button; workspace selection/default output beside PDFs; queue/progress.

### 9.1 Windows deployment: ready-to-use application

The user confirms deployment includes desktop, Start menu, and `PATH` integration. These are installation outcomes, not manual user steps.

| Item | Required behavior or technical proposal |
|---|---|
| Application installation | Per-user proposal under stable location such as `%LOCALAPPDATA%\Programs\SAMI`; separate executables from caches/models/diagnostics/documents. |
| Desktop | Create `SAMI.lnk` with own icon targeting installed graphical launcher. Resolve real OS desktop folder, including OneDrive redirection. |
| Start menu | Create user Programs entry `SAMI` to open UI/discover through Start search. Resolve Known Folders without constructing localized Windows paths. |
| Terminal | Stable `sami.exe` CLI launcher; additional proposed `sami-gui.exe` for terminal/shortcuts. Graphical executable names depend on chosen packaging. |
| `PATH` | Add only stable launcher directory to persistent user `PATH`, retaining other entries without duplicates. Exclude internal environments/temporary-version paths. |
| Graphical opening | Double-click desktop/Start opens UI without visible console, cwd dependence, or Python environment activation. |
| Application registration | Version/uninstaller in installed apps; stable identity between versions. |
| Update/repair | Stable shortcut/launcher targets, recoverable replacement, shortcut repair without duplicates. Preserve valid diagnostics/config for unchanged components. |
| Uninstall | Remove SAMI-created shortcuts/launchers/registration/`PATH` entry; retain originals/results; define model/cache cleanup separately. |

Microsoft documents Start shortcuts with Shell Links/`FOLDERID_Programs`; use Known Folders for desktop too. See [Start shortcuts](https://learn.microsoft.com/en-us/windows/win32/shell/how-to-add-shortcuts-to-the-start-menu), [Known Folder identifiers](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid).

Notify Windows of persistent `PATH` updates. Bootstrap can update its own PowerShell session, not promise to modify independently running terminals. UI shortcuts work immediately; test CLI in a process with refreshed environment. See [Windows environment variables](https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables).

With proposed Electron stack, use `electron-builder`/NSIS for graphical `.exe`, also invoked by `irm` bootstrap. NSIS exposes desktop/Start shortcuts; shared bootstrap remains responsible for CLI install/validation, path registration, `PATH`. Packaging Electron alone does not do those tasks. See [electron-builder NSIS](https://www.electron.build/v26/docs/nsis/). Driver steps remain explicit and independent.

UI opening reuses persisted diagnostics/core health. Clicking the icon does not repeat deep analysis. Shortcuts do not change workspace policy: PDFs retain source-based default destinations.

### 9.2 Proposed stack: Electron as CLI frontend

User priorities: useful/easy to code, CLI dependent; no need to share Python code or optimize package size/UI performance. Recommended design: **Electron + JavaScript + HTML/CSS**, distributed with `electron-builder`.

Electron presents web technology in an OS-packaged desktop application. Windows executable opens by double-click. Chromium/Node size is acceptable for the stated priorities. Users need not install Node.

| Part | Proposed choice | Purpose |
|---|---|---|
| Window/controls | Electron, simple HTML/CSS/JavaScript. | PDF list, options, buttons, progress/results; initially no component framework/web server. |
| Commands | `node:child_process.spawn` in Electron main process. | Invoke installed CLI, consume `stdout`/`stderr`, receive exits, manage cancellation through CLI protocol. |
| Window/process bridge | `preload.js`, `contextBridge`, specific IPC operations. | Health, convert, cancel, choose folders, open destinations/export results. |
| CLI protocol | Versioned health JSON and progress/results JSON Lines. | CLI owns conversion, compatibility, output paths, discovery, job states. |
| PDF viewer | Locally packaged PDF.js. | Embedded PDF preview. |
| Markdown viewer | markdown-it; KaTeX for equations as needed. | Local Markdown/resources/formula preview without changing generated files. |
| Graphical installation | electron-builder NSIS on Windows; evaluate DMG/macOS and AppImage/package/Linux. | OS artifacts/icons/distribution; CLI-first contract retained. |

Node asynchronous processes/I/O support a responsive UI during conversion. Use registered absolute executable and separate arguments, `shell: false`, `windowsHide: true`; do not concatenate filenames into commands. See [Node child_process](https://nodejs.org/api/child_process.html). This supplies terminal-command integration without embedded terminals/shell emulation.

Keep process access in main; expose specific window operations through [context isolation/contextBridge](https://www.electronjs.org/docs/latest/tutorial/context-isolation). CLI emits structured `stdout` events/`stderr` logs; UI handles transport fragments without interpreting human logs as progress. CLI cancellation closes owned processes, including Windows execution.

Inbound dragging uses file events/`webUtils.getPathForFile`; outbound uses native Electron dragging. See [file paths](https://www.electronjs.org/docs/latest/api/web-utils), [native drag and drop](https://www.electronjs.org/docs/latest/tutorial/native-file-drag-drop/). Main-process desktop operations open CLI-returned output directories.

Viewers use [PDF.js](https://mozilla.github.io/pdf.js/), [markdown-it](https://github.com/markdown-it/markdown-it), [KaTeX](https://katex.org/docs/browser). Bundle scripts/fonts/styles locally, no CDN. Controlled previews render table HTML/local resources; document content must not execute commands. UI displays CLI-produced files, not another PDF→Markdown converter.

UI is an independent project with its own `package.json`/versions and declared compatible CLI/protocol dependency. No `sami` library import, duplicated Python engines, or HTTP backend for communication. OS packaging coexists with separately distributed CLI.

Later prototype proposal: selection/drop, mode/output selection, run/cancel, two progress levels, open-results button. Add viewers/outbound drag afterward under the same contract. This sequence does not authorize implementation now.

Pending UX/validation:

- Outbound dragging exports real files through OS protocol. Receiver decides acceptance; literally every target cannot be guaranteed.
- Markdown with images is not self-contained. Propose exporting result folder/package with resources; define dragging only the `.md`.
- Initially copy on export; discuss moving separately to avoid broken paths/lost originals.
- Verify preview with Marker LaTeX/table HTML/images; adapt display without changing Markdown output.
- Keep UI responsive during preparation/conversion through shared supervisor. Graphical acceptance includes PDF navigation/zoom/search, errors, destination opening.

## 10. Validation required to accept the refactor

| Area | Evidence before claiming support |
|---|---|
| SAMI preservation | Compare Marker content/structure before/after on identical PDFs with pinned versions/models/equivalent options; explain material differences. |
| Fast engine | Simple native PDFs, columns, tables, images, scans with/without OCR; no silent page loss. |
| Selected fast profile | Compare the fast engine's `high/ocr=False/images=False` while retaining path/checks; no model loading/added random audit. |
| Embedded references | Retain bibliography in both engines, recoverable inline URL/DOI links/internal anchors; no external bibliography artifacts/network queries. |
| GPU fallback | Health/startup/execution failure: warning, CPU document retry, same mode, batch continuation without confirmation. Three CPU paths prepared at installation. |
| Three modes | Measure time, RAM/VRAM, coverage, reading order, table structure, equations/figures. Separate startup/download from steady conversion. |
| Hardware | No GPU, missing driver, incompatible runtime, multiple GPUs, low VRAM, unified memory, engine-test failure. |
| Persistence/health | Reuse positive/negative results; unknown schema, missing/corrupt profile, selective invalidation, no repeated deep CLI diagnostics; measure latency without network/models. |
| Installation | Clean OS installs without Python, compatible/incompatible existing runtime, no admin, no network, interrupted update. |
| Windows UI integration | Per-user bootstrap/installer, normal/redirected desktop, Start/search, no-console double-click, refreshed-environment CLI, duplicate-free reinstall, removing only SAMI integration. |
| CLI → UI deployment | Independent CLI; add UI to healthy CLI; detect incompatible versions; block graphical stage on core failure; retain CLI after UI failure; registered-path health; double-click independent of `PATH`/terminal/pending downloads. |
| Files | Unicode/spaces, recursive folders, duplicates, matching names, encryption, destination permissions, insufficient disk. |
| Recovery | Cancellation/document/publication failure; previous results intact, no owned active processes left behind. |
| CLI | Existing flags/agreed aliases, help without downloads, exit codes, actual progress, non-TTY use. |

The two `test-pdfs/` PDFs are a starting point, not sufficient coverage. Add a small representative corpus with reviewed expectations. Token retention helps detect loss, not independently certify fidelity/OCR quality.

Do not invent improvement percentages, seconds/page, universal VRAM thresholds without measurements. Tests are designed with implementation; none were created/run here.

## 11. Proposed work sequence after design discussion

| Phase | Reviewable outcome | Completion condition |
|---|---|---|
| 0. Decisions/feasibility | Agree modes/defaults, verify Marker dependencies per platform/backend. | Concrete matrix/viable CPU-GPU paths; uncertainty visible. |
| 1. Isolate current core | SAMI/Marker adapter, job/event contract. | Markdown conversion preserved against baseline. |
| 2. Diagnostics/runtimes | Persisted installation diagnostics, quick health, private preparation, explicit drivers. | Verified reuse/selective invalidation, measured startup, actual-engine test at installation. |
| 3. Profiles/CLI | Fast engine, folders/options/two progress levels. | Defined profiles, verifiable results, agreed CLI compatibility. |
| 4. Cross-platform install | `curl`/`irm`, ready independent CLI, health contract, tested packages/update. | Stable OS/architecture/acceleration matrix; CLI complete before UI. |
| 5. UI | Deployment stage gated by CLI health; OS package/Windows desktop-Start-`PATH` integration. | Install/reuse CLI, validate, then UI; verified double-click, graphical flows/export/viewers/update/uninstall. Separate delivery. |

Phases order decisions/deliverables; they are not execution authorization or schedule estimates.

## 12. Settled decisions and pending technical details

User-confirmed daily-use decisions:

| Topic | Final design decision |
|---|---|
| Default | `balanced`. |
| `fast` speed | Actual fast-engine configuration: `high`, OCR/images off. Preserve text/tables; verify comparable speed without heavy models. |
| References | Always retain bibliography/links in Markdown, without removal/external bibliography dependencies. |
| Existing result | Create a numbered output, retain previous. |
| Initial installation | Prepare all three modes/CPU fallback; no additional installation prompts in normal use. |
| Acceleration failure | Warn/automatically continue CPU, no GPU-related blocking/confirmation, same mode. |
| Platforms | Windows 11/Debian-based Linux priorities; secondary macOS. |

Technical details remaining before/during validation: Debian/Ubuntu versions/architectures; verified GPU/runtime combinations; per-engine capability flags; protocol versioning; atomic Markdown/resource publication. Retained technical proposal: `balanced → Marker fast`, `quality → Marker balanced`, corpus-validated without abandoning SAMI conversion preservation.

Also retain installation-only persisted deep diagnostics, fast normal health, local/keyless conversion, explicit drivers, CLI before UI, later Electron desktop/Start/`PATH` deployment. **Settling these decisions does not authorize implementation yet.**

## 13. Branches, work units, and files to change

### 13.1 Two branches and integration order

| Order | Exact branch | Base/target | Scope/completion condition |
|---|---|---|---|
| 1 | `refactor/0_2_0_sami_cli` | Updated `main`; PR to `main`. | Core, three modes, persisted diagnostics, quick health, CPU fallback, CLI/installers/CI. Independent installation/conversion without UI. |
| 2 | `feat/0_3_0_sami_ui` | `main` after CLI `0.2.0` merge/publication; PR to `main`. | Electron UI `0.3.0`, published CLI contract, graphical installer/shortcuts/double-click validation. |

These are the two requested development branches. Do not create branches/commits/PRs, merge, or publish while writing this plan. UI starts after complete CLI, avoiding duplicated changes or a PR targeting an intermediate branch.

Updated version decision: **`0.2.0` delivers complete independent CLI; `0.3.0` delivers UI**. Publish `v0.2.0` after CLI refactor without waiting for graphics, then develop/merge/publish `v0.3.0`. Both tags keep commits/assets; do not retroactively add UI to `v0.2.0`.

Split commits by complete behavior with tests/docs. CLI: preserve Marker; persisted diagnostics/runtime; fast-engine/reference/output policy; batch/progress/protocol; installation/release. UI: health/CLI execution; queue/progress/cancel; viewers/drag; packaging/Windows integration. Each unit declares verification/rollback.

Expected scope risks exceeding 400 lines/PR. Record actual size and review units; commit splitting is not multiple small PRs. Retain requested two branches, no subbranch chain. For over-budget PRs, document rationale/review strategy without compressing code/deleting comments.

### 13.2 CLI branch: existing files to edit

| Existing file | Planned change |
|---|---|
| `sami/cli.py` | Public entry: modes/defaults, files/folders, options/progress, health/doctor/setup, JSON/exit codes. Extract responsibilities while preserving Marker/agreed compatibility. |
| `sami/__init__.py` | Target `0.2.0`, consistent with metadata/version output. |
| `pyproject.toml` | Bump `0.2.0`; dependencies, entry point, packaging/dev/tests. Separate base/runtime variants while fully installing all modes. |
| `requirements.txt` | Align packaging/validated versions; avoid contradictory lists or generic `pip install` replacing prepared CPU/CUDA/ROCm variant. |
| `install.sh` | Versioned Debian-based bootstrap: all components, CPU/GPU, persisted health, command setup; release/manifest instead of moving `main`. |
| `setup.sh` | Align install/repair/update with shared preparation, three modes/CPU fallback; avoid divergent old recipe. |
| `.gitignore` | Temporary outputs/environments/local caches-models/test-build artifacts; keep source/manifests/locks. |
| `README.md` | `0.2.0`, complete install, modes/folders/health/permanent references/numbered outputs/fallback; mode-name migration. |
| `CLAUDE.md` | Architecture, commands/platforms, installation preparation, tool/agent contract. |
| `.claude/agents/convert.md` | Modes, input folders, outputs, permanent references. |
| `.claude/agents/install-check.md` | Replace first-conversion-download assumptions with full-install/persisted-health checks; Windows/CPU. |
| `.claude/agents/test.md` | Cases/expectations per engine, references/links, numbering/fallback; label historical results accordingly. |
| `test-pdfs/gen_test.py` | Extend only for reproducible references/links/tables/acceptance structures; retain current PDFs unless regeneration is necessary. |
| This plan | Final decisions, validation evidence, relationship to branches/releases. |

The reference extraction code (removed from the repository) was reading context for extraction, not a production module or a second maintained implementation. `cpu_monitor.py` needs no functional change absent demonstrated necessity. `.atl/` is unrelated local data.

### 13.3 CLI branch: proposed new files/directories

Module names map responsibilities; merge modules if simpler while retaining boundaries/contracts. Do not create empty modules merely to match the table.

| Proposed new file/directory | Responsibility |
|---|---|
| `sami/engines/__init__.py` | Engine contract/selection with deferred imports. |
| `sami/engines/marker.py` | Current SAMI/Marker pipeline, profiles/events; preserve conversion rules. |
| `sami/engines/fast.py` | Extracted/configured fast engine without global notebook execution/automatic random audit. |
| `sami/hardware.py` | Full installation inventory/light resource queries. |
| `sami/compatibility.py` | Persisted profile/schema/fingerprints, quick health, selective invalidation. |
| `sami/runtime.py` | Resolve/prepare/validate three modes/private runtimes, update/repair. |
| `sami/processes.py` | Owned process supervision, cross-platform cancellation, CPU recovery. |
| `sami/jobs.py` | Files/folder discovery, deduplication, ordering, batch execution. |
| `sami/outputs.py` | Destinations, numbering, staging, coherent Markdown/resource publication. |
| `sami/events.py` | Versioned event/result/job-control contract emitted by CLI, consumed by UI. |
| `sami/validation.py` | Explicit-scope consistency/reporting without rewriting Marker Markdown. |
| `install.ps1` | Complete Windows 11 per-user bootstrap, `PATH`, location/version/health. Later UI installation only after CLI validation. |
| `packaging/runtime-manifest.json` | Published runtime/version/model/source/verification combinations per platform; no personal machine diagnostics. |
| `packaging/constraints/` and chosen manager lock | Reproducible base/validated CPU-CUDA-ROCm variants; exact format depends on preparation mechanism. |
| `tests/` | Marker preservation, fast engine, health/cache, fallback/folders/outputs/protocol; small link/reference/scan fixtures, no models downloaded per unit test. |
| `.github/workflows/ci.yml` | PR/`main` unit checks, artifact smoke on priority platforms. |
| `.github/workflows/release.yml` | Verified tag/commit builds, assets/checksums/draft/final publication; extended in UI stage. |
| `CHANGELOG.md` | `0.2.0` changes/migration; do not invent historical `0.1.0` releases. |
| `docs/releasing.md` | Reproducible release/recovery runbook from sections 14/15: CLI `0.2.0`, UI `0.3.0`. |

Persisted diagnostics/models belong in private local installation state, not repository files or release uploads.

### 13.4 UI branch: new files and integration points

| Proposed new file/directory | Responsibility |
|---|---|
| `ui/package.json`, `ui/package-lock.json` | Independent Electron app `0.3.0`, dependencies/dev/build scripts, no copied Python engine. |
| `ui/src/main.js` | Window, CLI location/health/`spawn`/events/cancel, OS operations. |
| `ui/src/preload.js` | Limited UI–main bridge. |
| `ui/src/index.html`, `ui/src/renderer.js`, `ui/src/styles.css` | Inputs/options/queue, two progress levels, results/graphical recovery. |
| `ui/src/viewers/` | PDF.js, markdown-it/KaTeX, local resources. |
| `ui/assets/` | OS icons/bundled application resources. |
| `ui/electron-builder.yml` | Stable identity/packaging, Windows NSIS/shortcuts/metadata; secondary targets according to matrix. |
| `ui/tests/` | Health/protocol with test CLI, Unicode paths, fragmented events, errors/cancel/essential UI flows. |
| `packaging/windows/` | Minimal NSIS customization for CLI dependency/registration/install lifecycle when needed. |

Edit shared files in UI branch: `install.ps1`/`install.sh` add graphical stage; `packaging/runtime-manifest.json` declares UI `0.3.0`/compatible published CLI `0.2.x`; `.github/workflows/ci.yml`/`release.yml` add UI build/smoke; `.gitignore`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/releasing.md` cover complete installation/use. Change CLI only for demonstrated public-contract gaps, with tests and no Electron conversion duplication.

Keep `ui/package.json`/lock synchronized at `0.3.0`. Unchanged Python retains CLI `0.2.x`; do not bump to `0.3.0` merely to match UI. CI validates each component's own version/protocol compatibility from manifest. Installer pins exact tested CLI, not any unchecked `0.2.x`.

## 14. CLI release `0.2.0` after merge into `main`

### 14.1 Baseline and publication condition

Verified during this conversation: code declares `0.1.0` in `pyproject.toml`/`sami/__init__.py`; GitHub has no published releases/tags. Current installer consumes repository. This document neither changes version nor publishes: it plans CLI `0.2.0`/UI `0.3.0`.

Publish `0.2.0` after CLI branch merge, passing CI/installation tests and artifacts from one verified `main` commit. UI is neither requirement nor asset. Windows 11/Debian-based mandatory, macOS secondary/nonblocking and not advertised as verified without tests.

### 14.2 Preparation before tagging

1. Complete/verify `refactor/0_2_0_sami_cli`: original SAMI/fast-engine comparisons, three modes, full CPU installation/persisted health, inline references/links, numbering/fallback warnings. Merge PR into `main`.
2. Close CLI without UI: modes/public protocol/health/full installers/command on `PATH`. No graphical shortcuts or advertised UI `.exe` in `0.2.0`.
3. Include version bumps/notes in CLI PR: Python `0.2.0`, lock/manifest/changelog/docs. No unmerged local changes after candidate validation.
4. Record exact candidate SHA merged into `main`; run trial CI/build/version/package smoke. Merge fixes and revalidate new SHA before tagging.
5. Final matrix: clean installation without Python, three modes without later downloads, quick health, real GPU/CPU-fallback evidence, update/uninstall/document preservation. CPU runner does not demonstrate CUDA/ROCm.
6. Installer resolves versioned CLI `0.2.0` artifacts/checksums, not moving `main`. Document mode meaning changes, permanent references, UI scheduled for `0.3.0`.

### 14.3 Tag, build, publication

1. After CLI merge/checks, synchronize `main`; verify clean candidate contains PR and `v0.2.0` does not exist. Create annotated **`v0.2.0` on that exact SHA**, push only that tag. No development-branch tagging or indiscriminate `git push --tags`.
2. Release workflow present in tagged commit triggers from tag, checks `main` ancestry/version consistency; builds from tag, never a moving branch tip.
3. Platform jobs build/verify Python/CLI packages/installers. Keep CI artifacts for tests, also attach final files to Releases: temporary Actions artifacts do not replace public installer assets.
4. Smoke-test packages, checksum final bytes. Publication job depends on all required targets; only that job needs release-write permissions. Pin tools/actions during implementation.
5. Create **draft release** `0.2.0` at tag, attach assets/notes. Test bootstrap against those downloads using draft access/identical artifacts; do not announce public operational URLs before publication.
6. Verify manifest/checksums/names/versions/full installation/CLI using final assets. Publish stable `0.2.0` as **Latest** only afterward; later `0.3.0` may replace Latest without altering `0.2.0` CLI assets.
7. After publication, verify public `irm`/`curl`, assets/new installation/health. Record SHA/tag/release URL/workflow run IDs/actual outcomes in delivery closure.

See [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository) for drafts/tags/assets. Push tags with authorized maintainer identity; do not assume tags created by `GITHUB_TOKEN` trigger another `push` workflow, due to recursion prevention in [Actions triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

After a failed build, fix/retry appropriately without moving tags. Defects in tagged code require a new version, not silent stable-release byte replacement. Until checks finish, draft is not a usable release.

### 14.4 Expected artifacts and final acceptance

| Proposed asset | Contents/use |
|---|---|
| Python wheel/sdist `0.2.0` | CLI/core metadata/distribution; installer manages pinned runtimes/models. PyPI is a separate decision, not required for this GitHub release. |
| `install.ps1`, `install.sh` | `0.2.0` complete CLI bootstraps/components from manifest, no graphical stage yet. |
| Component manifest `0.2.0` | Artifact/model URLs/identities/checksums/dependencies/protocol; no personal diagnostics/credentials. |
| `SHA256SUMS`, release notes | Final-asset integrity, changes/mode migration/tested platforms/known limits. |
| macOS asset if validated | Optional for `0.2.0`; no untested file just to suggest complete coverage. |

Large models/runtimes may download from pinned/verifiable manifest sources during installation; no need to duplicate as release assets. Installation is complete only when all three modes are ready locally.

Final `0.2.0` acceptance: a Windows 11/Debian-based matrix machine installs via bootstrap, runs CLI without UI, uses all modes without further installs, preserves references/results, checks health quickly, and warns/continues CPU on GPU failure. **These steps are planned only, not executed in this task.**

## 15. UI release `0.3.0` on published CLI

### 15.1 Development and versioned dependency

After publishing CLI `0.2.0`, create `feat/0_3_0_sami_ui` from updated `main`; implement sections 9/13.4. UI `0.3.0` depends on CLI `0.2.x`/protocol with exact tested version pinned. Graphical-product version changes do not force rebuilding/renaming unchanged CLI packages.

If UI requires a CLI fix, publish a new component version/update dependency explicitly. Do not modify published `0.2.0` wheels/models. Validate claimed compatibility with actual bootstrap-installed versions.

### 15.2 Merge, tag, publication

1. Verify UI/integration: clean CLI→health→UI, add UI to healthy CLI, double-click/desktop/Start/`PATH`, viewers/drag/progress/cancel/CPU fallback.
2. Update UI/lock to `0.3.0`, manifest/changelog; retain actual CLI version. Extend CI/release for per-component versions/graphical build selection on `v0.3.0`.
3. Merge UI PR into `main`, pin candidate SHA, pass CI/package tests for that exact revision. CLI `0.2.0` remains independently available.
4. Create/push annotated **`v0.3.0`** on verified `main` commit. Follow section 14.3 tag builds/asset smoke/checksums/draft/publication; do not build a fictitious CLI `0.3.0` if its version is `0.2.x`.
5. Publish UI installer/full bootstraps resolving graphical `0.3.0` and published compatible CLI separately. Dependency URLs pin versions, not another component's blind `latest`.
6. Verify public clean installs/readiness/existing-CLI reuse. Publish `0.3.0` as Latest when required targets pass; retain `v0.2.0` for CLI-only installs.

### 15.3 Artifacts and acceptance

| Proposed asset | Contents/use |
|---|---|
| `SAMI-0.3.0-win-x64-setup.exe` | Electron/NSIS gated by CLI health; desktop/Start shortcuts. |
| `SAMI-0.3.0-linux-x64.AppImage` or validated Debian package | Tested Linux UI target depending on published CLI contract. |
| `install.ps1`, `install.sh` for `0.3.0` | Coordinate both stages/CLI-only; reuse compatible CLI without repeated deep diagnosis. |
| Product manifest `0.3.0` | UI identities/checksums, exact tested CLI `0.2.x`, compatible protocol. |
| `SHA256SUMS`, `0.3.0` notes | Integrity/features/required components/actually tested platforms. |
| macOS asset if validated | Secondary/nonblocking with documented evidence. |

Complete installation prepares missing CLI, checks health, installs UI. Double-click executable/shortcuts opens without console/Python activation/pending installs. UI consumes CLI commands/events only, no duplicated engines. Users can continue CLI-only `0.2.0` use. **Updating this plan creates no branches, tags, packages, or releases.**
