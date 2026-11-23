# 03 — Complete CLI, validation, and release 0.2.0

Date: 2026-11-18, America/Bogota. Status: specification for future implementation.
Future branch: `refactor/0_2_0_sami_cli`. Units U06–U07.
Depends on [01 — engines/contract](01-cli-contracts-engines-outputs.md) and [02 — installation/runtime](02-cli-diagnostics-runtime-installation.md).
UI starts only after publishing this delivery: [plan 04](04-ui-electron-application-0.3.0.md).

## Stage outcome

An independent CLI that fully installs, converts files/folders, preserves references/results, displays real progress, and provides a stable protocol. Its merge into `main` enables publishing `v0.2.0`; UI and Node are not required.

## U06 — Public interface, batches, and progress

### Files

| Current/future file | Change |
|---|---|
| `sami/cli.py` | Lightweight parser/dispatch, defaults, errors, and presentation. Retaining argparse avoids adding another command framework unnecessarily. |
| `sami/jobs.py` | Deterministic discovery, deduplication, document coordination, and results. |
| `sami/progress.py` | Event-to-terminal presentation adapter; JSON bypasses progress bars. |
| `sami/events.py`, `contracts.py` | Finalize contract, codes, counters, and compatibility tests for the future UI consumer. |
| `sami/outputs.py`, `processes.py` | Integrate numbering, CPU retry, and cancellation with batches. |
| `tests/test_cli.py`, `test_jobs.py`, `test_progress.py`, `tests/integration/` | Terminal behavior and programmatic consumer tests. |

### Proposed minimum 0.2.0 grammar

```text
sami INPUT [INPUT ...] [options]
sami convert INPUT [INPUT ...] [options]
sami health [--json]
sami doctor [--json]
sami setup
sami --help
sami --version
```

Preserve the direct form; `convert` is an explicit form useful for scripts. Resolve reserved subcommand-name ambiguity with explicit parsing and `convert -- path` when necessary. Do not infer a subcommand from the first PDF's extension.

| Minimum option | Behavior |
|---|---|
| `--mode fast\|balanced\|quality` | Default `balanced`; mapping from plan 01. |
| `-o/--output DIR` | Output root; otherwise beside each input. |
| `--recursive` | Search PDF subdirectories within directory inputs. Without it, only the first level. |
| `--flat` | No per-document subdirectory; resources still use unique namespaces. |
| `-q/--quiet` | No progress bars or informational logs; errors and fallback warnings remain visible. |
| `--no-strip-refs` | Compatibility: references are always preserved. No reference-removal flag. |
| `--device auto\|cpu\|cuda\|rocm` | Proposed resource control; final selection follows health. Even an explicitly requested GPU falls back to CPU with a warning on failure, as required. |
| `--json` | Conversion JSONL on stdout, human logs/warnings on stderr; warnings also appear as events. |
| `--control-stdin` | Structured protocol cancellation; do not read stdin in normal terminal mode. |

Do not use hardware to automatically change `balanced` to `fast`. Device and content profile are separate controls. Add macOS/MPS selection only after verifying its secondary scope; do not accept options that will be ignored.

Earlier proposals remaining in the technical backlog: page ranges/limits, OCR/languages, images, markers, tables, and configurable concurrency. These are not required to preserve current SAMI options. If included in `0.2.0`, first define capabilities/defaults per engine and test them; `fast` retains OCR/images off and the fast engine's speed by default. Do not expose a flag that an engine accepts but does not apply.

### Document discovery

1. Expand user paths, check inputs, and enumerate `.pdf` case-insensitively by extension.
2. Traverse directories according to the flag; do not follow directory links by default, avoid cycles, and exclude owned output/staging paths.
3. Deduplicate identity/normalized paths according to the OS. Do not lowercase every Linux path or assume all macOS filesystem variants behave identically.
4. Work order: explicit input order; within a directory, deterministic relative name order. The first occurrence retains its position after deduplication.
5. Create jobs/issues for invalid explicit inputs without abandoning valid ones. A broken/encrypted PDF fails individually; the next document continues.

Initially execute documents sequentially, as current SAMI does, with a worker/model reusable per batch where possible. CPU thread tuning does not mean launching multiple VLM servers. Do not introduce document parallelism without memory measurements and inference coordination.

Empty directory: clear message and selection error; do not load models. Do not modify or move inputs. Discarded duplicates are discovery information, not failed jobs.

### Progress and output

Presentation recommendation: Rich with a batch bar and a document task; [Rich supports multiple tasks and indeterminate progress](https://rich.readthedocs.io/en/stable/progress.html). Pin its version during implementation and declare a direct dependency if used.

The batch represents terminal documents/unique total. The document shows name, stage, pages or other actual units, and elapsed time. CPU retry resets attempt progress and does not increment the batch twice. Use indeterminate activity for Marker stages without counters; do not invent percentages across stages.

Without TTY: readable lines without control codes. With JSON: only events on stdout, without Rich; separate stderr. Limit visual event frequency without losing starts, endings, or warnings. The summary returns final paths and totals by status.

### Proposed exit codes

| Code | Conversion | Management |
|---|---|---|
| 0 | All jobs completed without gaps; GPU→CPU warnings do not change success. | Health `ready/degraded`; complete setup. |
| 1 | Some document `failed/partial`, without preventing others. | Explicit installation/preparation failure. |
| 2 | Invalid syntax/incompatible options or selection without PDFs. | Invalid usage. |
| 3 | Installation incomplete with no recoverable CPU runtime. Never use for GPU failure. | Health `repair_required`. |
| 130 | Requested cancellation, with cleanup and previous results preserved. | Preparation cancellation where supported. |

If an explicit input is missing while others are valid, record that input's failure and exit 1 after finishing the rest. Do not turn argument errors or installation corruption into GPU errors. In JSON mode, represent execution errors as events; errors before startup receive a structured error response when the mode can be identified, plus the exit code.

### U06 tests and completion

Cases: one file, multiple files, nonrecursive/recursive directory, mixed inputs, duplicates, `.PDF`, links/cycles, Unicode, empty, broken, reference, second output, and flat. An external JSON consumer checks framing, final state, and counters during fallback/cancellation. Test terminal, pipe, and quiet.

Future validation examples, available only after implementation:

```text
python -m pytest tests/test_cli.py tests/test_jobs.py tests/test_progress.py
sami test-pdfs/test_document.pdf --mode fast --json
sami test-pdfs/test_document.pdf --mode balanced
sami test-pdfs/radio_env_5pages.pdf --mode quality
sami health --json
```

Use a temporary output directory. Fast tests inject adapters; acceptance runs use real engines and prepared caches. **Rollback:** revert coordinator/presentation while preserving contracts and published results.

## U07 — CI, documentation, and CLI release

### Completion files

| File | Work |
|---|---|
| `pyproject.toml`, `sami/__init__.py` | Version `0.2.0`, consistency checks, and installed commands; preserve Python limits verified in U00. |
| `requirements.txt`, locks/constraints | Same resolution used by installation; no incompatible instructions. |
| `.github/workflows/ci.yml` | Fast PR/main checks, import/help, contract, Python build, and CPU smoke per platform. |
| `.github/workflows/release.yml` | CLI tag `v0.2.0`, builds/checksums, draft, assets, validation, and publication. |
| `.gitignore` | Ignore environments/models/results, not manifests/locks. |
| `README.md`, `CLAUDE.md` | Usage, architecture, complete installation, fallback, and actual limitations. |
| `.claude/agents/convert.md`, `install-check.md`, `test.md` | Remove first-download-during-conversion assumptions; update tests/defaults. Do not apply historical figure expectations to the fast engine with images off. |
| `CHANGELOG.md`, `docs/releasing.md` | `0.2.0` notes, migration, and reproducible runbook. |

Do not modify `cpu_monitor.py` without a demonstrated need. Do not include `.atl/`, caches, or personal diagnostics in commits/assets. Retain the reference extraction code as context, not as a production package.

### Acceptance matrix

| Group | Required evidence |
|---|---|
| Contracts and logic | Fast tests without network/models, valid stdout, side-effect-free help, and output invariants. |
| Engines | U00 corpus results for both Marker profiles and the fast engine; text, tables, equations/figures where applicable, and links. |
| CPU installation | Windows 11 and Debian-based matrix: no preinstalled Python, all three modes prepared, conversion with network blocked. |
| Acceleration | Real hardware for each advertised combination; verify actual VLM server/device and failure→CPU. A hosted CPU runner does not demonstrate GPU support. |
| Persistence | Second execution without deep diagnostics, measured health, negative cache, and selective changes. |
| Recovery | Interrupted download, failed publication, process-tree cancellation, update, and uninstall; documents intact. |

The minimum corpus adds links/annotations, bibliography, columns, complex tables, a scan, illegible text, and repeated filenames. Do not require OCR from the chosen `fast`: expect `partial` with an explanation. Do not equate token coverage with visual fidelity.

CI separates fast tests from runtime/installation tests. Build tests use the artifacts later distributed. Choose runner images and Linux baseline after U00; macOS may run as secondary/nonblocking without advertising untested support.

### 0.2.0 publication sequence

1. Complete U00–U07 and documentation in `refactor/0_2_0_sami_cli`. Record commits, outcomes, and scope. The CLI must work fully without Electron/Node.
2. Review and merge the PR into `main`. Pin the candidate SHA; do not tag the development branch or include unmerged local changes.
3. Trial build from that SHA: consistent Python `0.2.0`, lock, manifest, and changelog. Smoke-test assets on required platforms.
4. Create/push annotated tag `v0.2.0` on that SHA. The workflow checks tag/version and that the commit is merged into `main`.
5. Build wheel/sdist and bootstraps/manifest from the tag. Generate `SHA256SUMS` over final bytes. Create a draft and attach assets; an Actions artifact does not replace a public release asset.
6. Verify complete installation against the same assets, subsequent offline operation, health, and conversion. Publish stable as Latest once required targets pass.
7. Test public `irm/curl` URLs, assets, and health; save SHA/tag/run/results. Do not publish a graphical installer or UI shortcuts in this release.

Minimum assets: wheel/sdist `0.2.0`, `install.sh`, `install.ps1`, manifest, checksums, and notes. Models/runtimes may use pinned, verified external sources; installation must finish with them downloaded. PyPI is a separate decision.

If a build fails, do not announce the draft as ready. Do not move the tag to another commit or replace a consumed stable release; published code fixes require a new version. If a workflow creates the tag, account for `GITHUB_TOKEN` recursion restrictions; prefer an explicit maintainer tag or a well-defined dispatch.

### Delivery completion

A machine in the matrix installs CLI, uses all three modes without network/further installation, checks health quickly, retains references, receives numbered outputs, and continues on CPU after GPU failure. Publish `v0.2.0`. Only then begin `feat/0_3_0_sami_ui`.

Operational sources: [GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository), [Actions triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow). These are future steps, not actions executed while writing this plan.
