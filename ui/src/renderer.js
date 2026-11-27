import i18next from "i18next";
import localeCatalog from "./locales/i18n.json";
import { PdfPreview } from "./viewers/pdf.js";
import { renderMarkdown } from "./viewers/markdown.js";

const byId = (id) => document.getElementById(id);
const persistent = window.localStorage;
const preferredLocale = (navigator.language || "en").toLowerCase().startsWith("es") ? "es" : "en";
const state = {
  locale: persistent.getItem("sami.locale") || preferredLocale || localeCatalog.meta.default_locale || "en",
  theme: persistent.getItem("sami.theme") || "system",
  health: null,
  selected: [],
  output: null,
  results: [],
  issues: [],
  currentResult: null,
  activeFile: null,
  total: null,
  completed: 0,
  runStartedAt: null,
  stageStartedAt: null,
  stage: null,
  stageKey: null,
  percent: null,
  device: null,
  waiting: false,
  cancelling: false,
  operation: null,
  preview: null,
  previewTab: "markdown",
  toastTimer: null,
  renderSequence: 0,
  lastDiagnostics: [],
};

await i18next.init({
  lng: state.locale,
  fallbackLng: "en",
  resources: {
    en: { translation: localeCatalog.en },
    es: { translation: localeCatalog.es },
  },
  keySeparator: false,
  interpolation: { prefix: "{", suffix: "}", escapeValue: false },
});

const pdfPreview = new PdfPreview({
  canvas: byId("pdf-canvas"),
  pageLabel: byId("pdf-page-label"),
  zoomLabel: byId("pdf-zoom-label"),
  previousButton: byId("pdf-prev"),
  nextButton: byId("pdf-next"),
  zoomInButton: byId("pdf-zoom-in"),
  zoomOutButton: byId("pdf-zoom-out"),
});

const staticText = {
  "app-subtitle": "app.subtitle",
  "health-label": "health.checking",
  "workspace-eyebrow": "workspace.eyebrow",
  "workspace-title": "workspace.title",
  "browse-files-label": "action.browse",
  "add-folder-label": "action.addFolder",
  "setup-title": "action.prepareTitle",
  "setup-description": "action.prepareDescription",
  "setup-button": "action.prepare",
  "drop-title": "drop.title",
  "drop-subtitle": "drop.subtitle",
  "drop-browse": "action.chooseFiles",
  "selection-title": "selection.title",
  "clear-selection": "selection.clear",
  "empty-copy": "selection.placeholder",
  "options-title": "mode.label",
  "mode-help": "mode.help",
  "mode-label": "mode.label",
  "recursive-label": "mode.recursive",
  "flat-label": "mode.flat",
  "output-label": "output.label",
  "choose-output": "output.choose",
  "clear-output": "output.clear",
  "convert-label": "action.convert",
  "run-eyebrow": "run.eyebrow",
  "run-heading": "run.heading",
  "overall-label": "run.overall",
  "cancel-button": "action.cancel",
  "cancel-note": "run.cancelNote",
  "diagnostics-summary": "run.diagnostics",
  "results-eyebrow": "results.eyebrow",
  "results-heading": "results.heading",
  "result-list-heading": "results.listTitle",
  "preview-markdown-tab": "results.markdown",
  "preview-pdf-tab": "results.pdf",
  "preview-empty-copy": "results.previewEmpty",
  "open-result-folder": "action.openFolder",
  "export-result": "action.export",
  "drag-result": "action.drag",
  "new-batch-button": "action.more",
  "settings-eyebrow": "settings.eyebrow",
  "settings-heading": "settings.heading",
  "language-label": "settings.language",
  "theme-label": "settings.theme",
  "settings-done": "settings.done",
};

function t(key, values) {
  return i18next.t(key, values);
}

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = value;
}

function applyLanguage() {
  document.documentElement.lang = state.locale;
  document.title = t("app.title");
  for (const [id, key] of Object.entries(staticText)) setText(id, t(key));

  const modeNames = {
    balanced: t("mode.balanced"),
    fast: t("mode.fast"),
    quality: t("mode.quality"),
  };
  for (const option of byId("mode-select").options) option.textContent = modeNames[option.value];

  const labels = {
    system: t("settings.theme.system"),
    light: t("settings.theme.light"),
    dark: t("settings.theme.dark"),
  };
  for (const option of byId("theme-select").options) option.textContent = labels[option.value];

  for (const [id, labelKey, titleKey] of [
    ["pdf-prev", "preview.prev", "preview.prev"],
    ["pdf-next", "preview.next", "preview.next"],
    ["pdf-zoom-in", "preview.zoomIn", "preview.zoomIn"],
    ["pdf-zoom-out", "preview.zoomOut", "preview.zoomOut"],
  ]) {
    byId(id).setAttribute("aria-label", t(labelKey));
    byId(id).title = t(titleKey);
  }
  byId("drop-zone").setAttribute("aria-label", t("access.drop"));
  byId("health-pill").setAttribute("aria-label", t("status.health"));
  byId("settings-button").setAttribute("aria-label", t("action.settings"));
  byId("settings-button").title = t("action.settings");
  byId("close-preview").setAttribute("aria-label", t("preview.close"));
  byId("close-preview").title = t("preview.close");
  byId("language-select").value = state.locale;
  byId("theme-select").value = state.theme;
  byId("mode-select").value = byId("mode-select").value || "balanced";
  if (state.health) updateHealth(state.health);
  renderSelection();
  renderRunState();
  if (state.results.length) renderResults();
}

function applyTheme(theme) {
  state.theme = theme;
  persistent.setItem("sami.theme", theme);
  if (theme === "system") {
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "light dark";
  } else {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }
  byId("theme-select").value = theme;
}

function niceName(path) {
  return path.split(/[\\/]/).filter(Boolean).at(-1) || path;
}

function pathKey(path) {
  const normalized = path.replaceAll("\\", "/");
  return /^(?:[a-z]:|\\\\)/i.test(path) ? normalized.toLocaleLowerCase() : normalized;
}

function showToast(key, values) {
  const toast = byId("toast");
  toast.textContent = t(key, values);
  toast.classList.remove("hidden");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.add("hidden"), 3600);
}

function showError(message) {
  const banner = byId("error-banner");
  banner.textContent = message;
  banner.classList.remove("hidden");
}

function clearError() {
  byId("error-banner").classList.add("hidden");
  byId("error-banner").textContent = "";
}

function formatDuration(milliseconds) {
  const seconds = Math.max(0, Math.floor((milliseconds || 0) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  const hours = Math.floor(minutes / 60);
  if (hours) return `${hours}:${String(minutes % 60).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function inputKind(path) {
  return /\.pdf$/i.test(path) ? "file" : "folder";
}

function addRows(paths) {
  const known = new Set(state.selected.map((item) => pathKey(item.path)));
  const accepted = [];
  for (const path of paths) {
    if (typeof path !== "string" || !path.trim()) continue;
    if (known.has(pathKey(path))) continue;
    known.add(pathKey(path));
    accepted.push({ path, kind: inputKind(path) });
  }
  state.selected.push(...accepted);
  renderSelection();
  return accepted.length;
}

function fileGlyph() {
  const wrapper = document.createElement("span");
  wrapper.className = "file-glyph";
  wrapper.setAttribute("aria-hidden", "true");
  wrapper.innerHTML = '<svg viewBox="0 0 24 24"><path d="M5 2.75h9l5 5V21H5zM14 2.75v5h5M8 13h8M8 16.5h6"/></svg>';
  return wrapper;
}

function renderSelection() {
  const list = byId("file-list");
  const empty = byId("empty-state");
  list.replaceChildren(empty);
  list.classList.toggle("empty", state.selected.length === 0);
  empty.classList.toggle("hidden", state.selected.length > 0);
  byId("clear-selection").classList.toggle("hidden", state.selected.length === 0);

  const count = state.selected.length;
  const selectedText = count === 1 ? t("selection.one", { count }) : t("selection.many", { count });
  setText("selection-summary", count ? selectedText : t("selection.empty"));
  setText("selection-count", count === 1 ? t("selection.one", { count }) : t("selection.many", { count }));
  const convertKey = count === 1 ? "action.convert" : "action.convertCount";
  setText("convert-label", t(convertKey, { count }));

  for (const [index, input] of state.selected.entries()) {
    const row = document.createElement("div");
    row.className = "file-row";
    row.append(fileGlyph());

    const copy = document.createElement("span");
    copy.className = "file-copy";
    const name = document.createElement("strong");
    name.className = "file-name";
    name.textContent = niceName(input.path);
    name.title = input.path;
    const path = document.createElement("small");
    path.className = "file-path";
    path.textContent = input.path;
    copy.append(name, path);

    const type = document.createElement("span");
    type.className = "file-kind";
    type.textContent = t(input.kind === "file" ? "input.file" : "input.folder");

    const remove = document.createElement("button");
    remove.className = "icon-button remove-file";
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `${t("action.remove")} ${niceName(input.path)}`);
    remove.addEventListener("click", () => {
      state.selected.splice(index, 1);
      renderSelection();
    });
    row.append(copy, type, remove);
    list.append(row);
  }
  updateControls();
}

function selectedMode() {
  return byId("mode-select").value || "balanced";
}

function selectedModeHealth() {
  return state.health?.modes?.[selectedMode()];
}

function updateHealth(health) {
  state.health = health;
  const pill = byId("health-pill");
  pill.classList.remove("ready", "degraded", "repair");
  const mode = selectedModeHealth();
  const ready = mode?.ready === true;
  const status = !health ? "checking" : ready ? (mode.device === "cpu" && selectedMode() !== "fast" ? "degraded" : "ready") : "repair";
  pill.classList.add(status);
  setText("health-label", t(`health.${status}`));

  const repairBanner = byId("setup-banner");
  const hasCli = Boolean(health?.paths?.executable);
  const showPrepare = !ready && hasCli;
  repairBanner.classList.toggle("hidden", !showPrepare);
  if (showPrepare) {
    setText("setup-title", t("action.prepareTitle"));
    setText("setup-description", t("action.prepareDescription"));
    setText("setup-button", t("action.prepare"));
  }

  const compatibility = byId("compatibility-note");
  compatibility.classList.add("hidden");
  compatibility.replaceChildren();
  if (ready && selectedMode() !== "fast" && mode.device === "cpu") {
    compatibility.textContent = t("health.cpu");
    compatibility.classList.remove("hidden");
  } else if (ready && mode.device === "cuda") {
    compatibility.textContent = t("run.device.cuda");
    compatibility.classList.remove("hidden");
  } else if (ready && mode.device === "rocm") {
    compatibility.textContent = t("run.device.rocm");
    compatibility.classList.remove("hidden");
  }
  updateControls();
}

function updateControls() {
  const busy = Boolean(state.operation);
  const modeReady = selectedModeHealth()?.ready === true;
  byId("convert-button").disabled = busy || state.selected.length === 0 || !modeReady;
  byId("browse-files").disabled = busy;
  byId("add-folder").disabled = busy;
  byId("drop-zone").setAttribute("aria-disabled", String(busy));
  for (const control of ["mode-select", "recursive-toggle", "flat-toggle", "choose-output", "clear-output"]) {
    byId(control).disabled = busy;
  }
}

async function refreshHealth() {
  try {
    const health = await window.sami.getHealth();
    updateHealth(health);
    return health;
  } catch (error) {
    state.health = null;
    const pill = byId("health-pill");
    pill.classList.remove("ready", "degraded");
    pill.classList.add("repair");
    setText("health-label", t("health.repair"));
    byId("setup-banner").classList.remove("hidden");
    byId("compatibility-note").classList.add("hidden");
    setText("setup-title", t("health.noCli"));
    setText("setup-description", t("health.repairLink"));
    setText("setup-button", t("health.repairLink"));
    showError(error.message || t("health.noCli"));
    return null;
  }
}

async function chooseFiles() {
  if (state.operation) return;
  try {
    const paths = await window.sami.selectFiles();
    const added = addRows(paths || []);
    if (added) showToast("toast.added", { count: added });
  } catch (error) {
    showError(error.message || t("toast.operationFailed"));
  }
}

async function chooseFolder() {
  if (state.operation) return;
  try {
    const paths = await window.sami.selectFolder();
    const added = addRows(paths || []);
    if (added) showToast("toast.added", { count: added });
  } catch (error) {
    showError(error.message || t("toast.operationFailed"));
  }
}

async function handleDrop(event) {
  event.preventDefault();
  byId("drop-zone").classList.remove("drag-over");
  if (state.operation) return;
  try {
    const paths = window.sami.dropPaths(Array.from(event.dataTransfer.files));
    const selected = await window.sami.addDroppedPaths(paths);
    const added = addRows(selected || []);
    if (added) showToast("toast.added", { count: added });
  } catch (error) {
    showError(error.message || t("toast.operationFailed"));
  }
}

function showScreen(screen) {
  byId("workspace").classList.toggle("hidden", screen !== "workspace");
  byId("run-view").classList.toggle("hidden", screen !== "run");
  byId("results-view").classList.toggle("hidden", screen !== "results");
}

function translateStage(raw) {
  const stage = String(raw || "");
  const lower = stage.toLowerCase();
  const step = lower.match(/^\[(\d+)\/(\d+)\]/);
  if (step) return t("stage.refine", { current: step[1], total: step[2] });
  if (/high-res/.test(lower)) return t("stage.render");
  if (/extracting text/.test(lower)) return t("stage.extract");
  if (/stripping references/.test(lower)) return t("stage.references");
  if (/writing \d+ figure/.test(lower)) return t("stage.figures");
  if (/reading pdf/.test(lower)) return t("stage.read");
  if (/building page structure|structure building/.test(lower)) return t("stage.structure");
  if (/layout detection/.test(lower)) return t("stage.layout");
  if (/line extraction/.test(lower)) return t("stage.line");
  if (/^ocr \(skipped/.test(lower)) return t("stage.ocrSkipped");
  if (/^ocr \(/.test(lower)) return t("stage.ocr");
  if (/markdown/.test(lower)) return t("stage.markdown");
  return stage || t("stage.unknown");
}

function describeProgress(data) {
  if (data.phase === "pages") return t("stage.pageProgress", { completed: data.completed, total: data.total });
  if (!String(data.phase || "").startsWith("model_")) return translateStage(data.stage);
  const parts = [t(`stage.${data.phase}`)];
  if (data.total > 0) {
    const key = data.unit === "block" ? "stage.blocksDone" : "stage.pagesDone";
    parts.push(t(key, { completed: data.completed, total: data.total }));
  }
  const format = (value) => new Intl.NumberFormat(state.locale).format(value);
  if (data.tokens > 0) parts.push(t("stage.tokens", { tokens: format(data.tokens) }));
  if (data.tokens_per_second > 0) parts.push(t("stage.rate", { rate: format(Math.round(data.tokens_per_second)) }));
  return parts.join(" · ");
}

function renderRunState(activity) {
  if (!state.operation) return;
  setText("elapsed-label", formatDuration(Date.now() - state.runStartedAt));
  setText("document-elapsed", formatDuration(Date.now() - state.stageStartedAt));
  if (state.stage) setText("active-stage", state.stage);
  if (state.activeFile) setText("active-file", niceName(state.activeFile));

  const total = state.total;
  setText("overall-count", total === null ? "…" : t("run.files", { current: state.completed, total }));
  const track = byId("overall-track");
  if (Number.isInteger(total) && total > 0) {
    track.classList.remove("indeterminate");
    track.setAttribute("aria-valuemax", String(total));
    track.setAttribute("aria-valuenow", String(Math.min(state.completed, total)));
    byId("overall-fill").style.width = `${Math.min(100, (state.completed / total) * 100)}%`;
  } else {
    track.classList.add("indeterminate");
    track.setAttribute("aria-valuemax", "100");
    track.removeAttribute("aria-valuenow");
  }

  const stageTrack = byId("stage-track");
  // The file percentage is an estimate; older CLIs only send item counts.
  const progressEvent = state.percent === null ? state.lastProgress : { completed: state.percent, total: 100 };
  setText("file-percent", state.percent === null ? "" : `~${state.percent}%`);
  if (progressEvent?.total > 0 && progressEvent.completed >= 0) {
    stageTrack.classList.remove("indeterminate");
    stageTrack.classList.add("measured");
    stageTrack.setAttribute("aria-valuenow", String(progressEvent.completed));
    stageTrack.setAttribute("aria-valuemax", String(progressEvent.total));
    byId("stage-fill").style.width = `${Math.min(100, (progressEvent.completed / progressEvent.total) * 100)}%`;
  } else {
    stageTrack.classList.add("indeterminate");
    stageTrack.classList.remove("measured");
    stageTrack.removeAttribute("aria-valuenow");
    byId("stage-fill").style.width = "";
  }

  const queued = total === null ? state.selected.length : Math.max(0, total - state.completed - (state.activeFile ? 1 : 0));
  const queuedText = queued === 1 ? t("run.waitingOne", { count: queued }) : t("run.queued", { count: queued });
  setText("queue-copy", queuedText);
  const device = state.device ? t(`run.device.${state.device}`) : "";
  setText("effective-device", device);
  byId("effective-device").classList.toggle("effective-device", Boolean(device));
  byId("waiting-notice").classList.toggle("hidden", !(activity?.waiting || state.waiting));
  if (activity?.waiting || state.waiting) {
    const silence = activity?.silenceMs ?? Date.now() - state.lastEventAt;
    setText("waiting-notice", t("run.waiting", { time: formatDuration(silence) }));
  }
  byId("cancel-button").disabled = state.cancelling;
  setText("cancel-button", state.cancelling ? t("run.cancelled") : t("action.cancel"));
}

function appendDiagnostic(value) {
  const text = typeof value === "string" ? value : value?.message;
  if (!text) return;
  state.lastDiagnostics.push(text);
  if (state.lastDiagnostics.length > 240) state.lastDiagnostics.shift();
  setText("diagnostics-log", state.lastDiagnostics.join("\n"));
  byId("diagnostics-panel").open = value?.level === "error";
}

function onRunnerEvent(event) {
  if (!event || event.protocol_version !== 1) return;
  state.lastEventAt = Date.now();
  state.waiting = false;
  if (event.event === "run_started") {
    state.runStartedAt = state.runStartedAt || Date.now();
    state.device = event.data.requested_device === "auto" ? (selectedModeHealth()?.device || "cpu") : event.data.requested_device;
    renderRunState();
  } else if (event.event === "inputs_resolved") {
    state.total = event.data.count;
    state.issues = event.data.issues || [];
    for (const issue of state.issues) appendDiagnostic(`${issue.path}: ${issue.message}`);
    renderRunState();
  } else if (event.event === "job_started") {
    state.activeFile = event.data.input;
    state.stage = t("stage.waiting");
    state.stageKey = null;
    state.percent = null;
    state.stageStartedAt = Date.now();
    state.device = event.data.device || state.device;
    state.lastProgress = null;
    showScreen("run");
    renderRunState();
  } else if (event.event === "job_progress") {
    const stage = describeProgress(event.data);
    // Live counters change the text, so the stage clock follows the phase.
    const stageKey = event.data.phase || stage;
    if (stageKey !== state.stageKey) state.stageStartedAt = Date.now();
    state.stageKey = stageKey;
    state.stage = stage;
    if (Number.isFinite(event.data.percent)) state.percent = Math.max(state.percent ?? 0, event.data.percent);
    // Keep the bar moving until there is a completed item to measure.
    state.lastProgress = event.data.completed > 0 && Number.isFinite(event.data.total)
      ? { completed: event.data.completed, total: event.data.total }
      : null;
    renderRunState();
  } else if (event.event === "job_retrying") {
    state.device = "cpu";
    state.stage = t("run.retrying");
    state.percent = null;
    state.stageStartedAt = Date.now();
    state.lastProgress = null;
    renderRunState();
  } else if (event.event === "warning") {
    appendDiagnostic(event.data.message || event.data.reason || t("results.error"));
  } else if (event.event === "job_finished") {
    const result = event.data?.result;
    if (result) {
      state.results = state.results.filter((item) => item.job_id !== result.job_id);
      state.results.push(result);
      state.completed += 1;
      state.activeFile = null;
      state.lastProgress = null;
      state.percent = null;
    }
    renderRunState();
  } else if (event.event === "run_finished") {
    state.operation = null;
    state.cancelling = false;
    updateControls();
    renderResults(event.data);
    showScreen("results");
  }
}

function resetRun() {
  state.results = [];
  state.issues = [];
  state.total = null;
  state.percent = null;
  state.completed = 0;
  state.runStartedAt = Date.now();
  state.stageStartedAt = Date.now();
  state.stage = t("run.starting");
  state.lastEventAt = Date.now();
  state.activeFile = null;
  state.waiting = false;
  state.cancelling = false;
  state.device = null;
  state.lastProgress = null;
  state.lastDiagnostics = [];
  setText("diagnostics-log", "");
  byId("diagnostics-panel").open = false;
  clearError();
}

async function startConversion() {
  if (state.operation || !state.selected.length) return;
  if (!selectedModeHealth()?.ready) {
    byId("setup-banner").classList.remove("hidden");
    return;
  }
  clearError();
  resetRun();
  state.operation = "conversion";
  showScreen("run");
  renderRunState();
  updateControls();
  const request = {
    inputs: state.selected.map((item) => item.path),
    mode: selectedMode(),
    recursive: byId("recursive-toggle").checked,
    flat: byId("flat-toggle").checked,
    output: state.output,
  };
  try {
    await window.sami.startConversion(request);
  } catch (error) {
    state.operation = null;
    updateControls();
    showScreen("workspace");
    showError(error.message || t("toast.operationFailed"));
  }
}

function warningCount(result) {
  return (result.warnings?.length || 0) + (result.errors?.length || 0) + (result.gaps?.length || 0);
}

function resultStatusLabel(status) {
  return t(`results.status.${status}`);
}

function renderResults(run = {}) {
  const successes = state.results.filter((item) => item.status === "succeeded").length;
  const partial = state.results.filter((item) => item.status === "partial").length;
  const failed = state.results.filter((item) => item.status === "failed").length;
  const cancelled = state.results.filter((item) => item.status === "cancelled").length;
  const wasCancelled = run.exit_code === 130 || cancelled > 0;
  const hasProblems = partial > 0 || failed > 0 || state.issues.length > 0 || Boolean(run.error);
  setText("results-heading", wasCancelled ? t("results.cancelledHeading") : hasProblems ? t("results.partialHeading") : t("results.heading"));
  const summary = t(wasCancelled ? "results.summaryCancelled" : "results.summary",
    { success: successes, partial, failed, cancelled });
  setText("results-summary", run.error?.message ? `${summary}. ${run.error.message}` : summary);
  const list = byId("result-list");
  list.replaceChildren();
  state.results.forEach((result) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "result-item";
    item.classList.toggle("selected", result.job_id === state.currentResult?.job_id);

    const badge = document.createElement("span");
    badge.className = `result-status ${result.status}`;
    badge.textContent = result.status === "succeeded" ? "✓" : result.status === "partial" ? "!" : result.status === "cancelled" ? "–" : "×";
    badge.setAttribute("aria-label", resultStatusLabel(result.status));

    const copy = document.createElement("span");
    copy.className = "result-item-copy";
    const name = document.createElement("strong");
    name.textContent = niceName(result.input_path);
    const status = document.createElement("small");
    status.textContent = resultStatusLabel(result.status);
    if (warningCount(result)) status.textContent += ` · ${t("results.warnings", { count: warningCount(result) })}`;
    copy.append(name, status);
    const open = document.createElement("span");
    open.className = "result-open";
    open.textContent = "›";
    item.append(badge, copy, open);
    item.addEventListener("click", () => void selectResult(result));
    list.append(item);
  });
  for (const issue of state.issues) {
    const row = document.createElement("div");
    row.className = "result-item";
    const badge = document.createElement("span");
    badge.className = "result-status failed";
    badge.textContent = "!";
    const copy = document.createElement("span");
    copy.className = "result-item-copy";
    const name = document.createElement("strong");
    name.textContent = niceName(issue.path);
    const reason = document.createElement("small");
    reason.textContent = issue.message;
    copy.append(name, reason);
    row.append(badge, copy);
    list.append(row);
  }
  if (!state.currentResult || !state.results.includes(state.currentResult)) {
    const first = state.results.find((result) => result.output_paths?.[0]);
    if (first) void selectResult(first);
  }
  if (!state.results.length) resetPreview();
}

function resetPreview() {
  state.renderSequence += 1;
  state.currentResult = null;
  state.preview = null;
  pdfPreview.destroy();
  byId("preview-empty").classList.remove("hidden");
  byId("markdown-preview").classList.add("hidden");
  byId("pdf-preview").classList.add("hidden");
  byId("preview-actions").classList.add("hidden");
  setText("preview-file-label", "");
}

async function selectResult(result) {
  state.currentResult = result;
  renderResultsListSelection();
  const markdownPath = result.output_paths?.[0];
  if (!markdownPath) {
    resetPreview();
    return;
  }
  state.renderSequence += 1;
  const sequence = state.renderSequence;
  byId("preview-empty").classList.remove("hidden");
  byId("markdown-preview").classList.add("hidden");
  byId("pdf-preview").classList.add("hidden");
  byId("preview-actions").classList.add("hidden");
  setText("preview-empty-copy", t("results.previewEmpty"));
  setText("preview-file-label", niceName(result.input_path));
  try {
    const preview = await window.sami.loadPreview({ pdfPath: result.input_path, markdownPath });
    if (sequence !== state.renderSequence) return;
    state.preview = preview;
    const html = renderMarkdown(preview.markdown || "", preview.resourceUrls || {}, t("results.resourceMissing"));
    const pane = byId("markdown-preview");
    pane.innerHTML = html;
    const missingImages = pane.querySelectorAll(".missing-resource-image");
    for (const image of missingImages) {
      const placeholder = document.createElement("div");
      placeholder.className = "preview-missing-resource";
      placeholder.textContent = t("results.resourceMissing");
      image.replaceWith(placeholder);
    }
    pane.querySelectorAll('[data-sami-missing-link="true"]').forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        showToast("results.linkMissing");
      });
    });
    const activeTab = state.previewTab;
    await showPreviewTab(activeTab);
    byId("preview-empty").classList.add("hidden");
    byId("preview-actions").classList.remove("hidden");
    renderResultsListSelection();
  } catch (error) {
    byId("preview-empty").classList.remove("hidden");
    setText("preview-empty-copy", error.message || t("results.previewError"));
  }
}

function renderResultsListSelection() {
  document.querySelectorAll(".result-item").forEach((item, index) => {
    item.classList.toggle("selected", state.results[index]?.job_id === state.currentResult?.job_id);
  });
}

async function showPreviewTab(tab) {
  state.previewTab = tab;
  const isMarkdown = tab === "markdown";
  byId("preview-markdown-tab").classList.toggle("active", isMarkdown);
  byId("preview-markdown-tab").setAttribute("aria-selected", String(isMarkdown));
  byId("preview-pdf-tab").classList.toggle("active", !isMarkdown);
  byId("preview-pdf-tab").setAttribute("aria-selected", String(!isMarkdown));
  byId("markdown-preview").classList.toggle("hidden", !isMarkdown || !state.preview);
  byId("pdf-preview").classList.toggle("hidden", isMarkdown || !state.preview);
  if (!state.preview) {
    byId("preview-empty").classList.remove("hidden");
    return;
  }
  byId("preview-empty").classList.add("hidden");
  if (!isMarkdown) {
    if (!state.preview.pdfUrl) {
      byId("preview-pdf-tab").disabled = true;
      byId("preview-empty").classList.remove("hidden");
      setText("preview-empty-copy", t("results.previewError"));
      byId("pdf-preview").classList.add("hidden");
      return;
    }
    byId("preview-pdf-tab").disabled = false;
    try {
      await pdfPreview.open(state.preview.pdfUrl);
    } catch (error) {
      byId("preview-empty").classList.remove("hidden");
      setText("preview-empty-copy", error.message || t("results.previewError"));
      byId("pdf-preview").classList.add("hidden");
    }
  }
}

async function prepareSami() {
  if (state.operation) return;
  state.operation = "setup";
  state.runStartedAt = Date.now();
  state.stageStartedAt = Date.now();
  state.stage = t("run.preparingModels");
  state.lastEventAt = Date.now();
  showScreen("run");
  setText("run-heading", t("run.preparingModels"));
  byId("cancel-button").classList.add("hidden");
  byId("overall-track").classList.add("indeterminate");
  byId("overall-count").classList.add("hidden");
  updateControls();
  renderRunState();
  try {
    const setup = !state.health?.paths?.executable && window.sami.repairInstallation
      ? await window.sami.repairInstallation()
      : await window.sami.setup();
    const health = await window.sami.getHealth();
    updateHealth(health);
    if (setup.failures?.length) {
      showScreen("workspace");
      showError(setup.failures.join("\n"));
    } else {
      showScreen("workspace");
      showToast("app.healthy");
    }
  } catch (error) {
    showScreen("workspace");
    showError(error.message || t("toast.setupFailed"));
  } finally {
    state.operation = null;
    byId("cancel-button").classList.remove("hidden");
    byId("overall-count").classList.remove("hidden");
    setText("run-heading", t("run.heading"));
    updateControls();
    await refreshHealth();
  }
}

async function cancelConversion() {
  if (!state.operation || state.operation === "setup" || state.cancelling) return;
  state.cancelling = true;
  renderRunState();
  try {
    await window.sami.cancelConversion();
  } catch (error) {
    state.cancelling = false;
    appendDiagnostic(error);
    showToast("toast.cancelFailed");
    renderRunState();
  }
}

function updateOutputPath() {
  setText("output-path", state.output || t("output.default"));
  byId("clear-output").classList.toggle("hidden", !state.output);
}

async function chooseOutput() {
  try {
    const output = await window.sami.selectOutput();
    if (output) {
      state.output = output;
      updateOutputPath();
    }
  } catch (error) {
    showError(error.message || t("toast.operationFailed"));
  }
}

async function openResultFolder() {
  if (!state.currentResult?.output_paths?.[0]) return;
  try {
    await window.sami.openOutputFolder(state.currentResult.output_paths[0]);
  } catch (error) {
    showToast("results.openError");
    appendDiagnostic(error);
  }
}

async function exportResult() {
  if (!state.currentResult?.output_paths?.[0]) return;
  try {
    const result = await window.sami.exportResult(state.currentResult.output_paths[0]);
    if (result) showToast("results.copySuccess");
  } catch (error) {
    showToast(error.message || t("toast.operationFailed"));
  }
}

async function dragResult() {
  if (!state.currentResult?.output_paths?.[0]) return;
  try {
    await window.sami.startResultDrag(state.currentResult.output_paths[0]);
  } catch (error) {
    showToast(error.message || t("toast.operationFailed"));
  }
}

function newBatch() {
  if (state.operation) return;
  state.selected = [];
  state.results = [];
  state.currentResult = null;
  state.issues = [];
  state.output = null;
  updateOutputPath();
  renderSelection();
  resetPreview();
  showScreen("workspace");
}

function handleDiagnostic(value) {
  appendDiagnostic(value);
  if (value?.level === "error" && !state.operation) showError(value.message);
}

function handleActivity(activity) {
  if (Number.isFinite(activity.elapsedMs) && state.operation) state.runStartedAt = state.runStartedAt || Date.now() - activity.elapsedMs;
  if (Number.isFinite(activity.silenceMs) && activity.silenceMs >= 0) state.waiting = activity.waiting === true;
  renderRunState(activity);
}

function handleState(value) {
  if (!value || typeof value !== "object") return;
  if (value.phase === "running" || value.phase === "checking-health" || value.phase === "preparing") {
    state.stage = value.phase === "preparing" ? t("run.preparingModels") : value.phase === "checking-health" ? t("run.checkingHealth") : state.stage;
    state.stageStartedAt = Date.now();
  }
  if (value.phase === "repair_required") {
    state.health = value.health || state.health;
    updateHealth(state.health || { modes: {} });
  }
  renderRunState();
}

function bindEvents() {
  byId("browse-files").addEventListener("click", () => void chooseFiles());
  byId("drop-browse").addEventListener("click", () => void chooseFiles());
  byId("add-folder").addEventListener("click", () => void chooseFolder());
  byId("clear-selection").addEventListener("click", () => {
    state.selected = [];
    renderSelection();
  });
  byId("drop-zone").addEventListener("dragover", (event) => {
    event.preventDefault();
    if (!state.operation) byId("drop-zone").classList.add("drag-over");
  });
  byId("drop-zone").addEventListener("dragleave", (event) => {
    if (!event.relatedTarget || !byId("drop-zone").contains(event.relatedTarget)) byId("drop-zone").classList.remove("drag-over");
  });
  byId("drop-zone").addEventListener("drop", (event) => void handleDrop(event));
  document.addEventListener("dragover", (event) => {
    if (event.dataTransfer?.types?.includes("Files")) event.preventDefault();
  });
  document.addEventListener("drop", (event) => {
    if (byId("drop-zone").contains(event.target)) return;
    if (event.dataTransfer?.types?.includes("Files")) event.preventDefault();
  });
  byId("drop-zone").addEventListener("keydown", (event) => {
    if (event.target !== byId("drop-zone")) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      void chooseFiles();
    }
  });
  byId("convert-button").addEventListener("click", () => void startConversion());
  byId("mode-select").addEventListener("change", () => {
    updateHealth(state.health);
  });
  byId("choose-output").addEventListener("click", () => void chooseOutput());
  byId("clear-output").addEventListener("click", () => {
    state.output = null;
    updateOutputPath();
  });
  byId("setup-button").addEventListener("click", () => void prepareSami());
  byId("cancel-button").addEventListener("click", () => void cancelConversion());
  byId("new-batch-button").addEventListener("click", newBatch);
  byId("preview-markdown-tab").addEventListener("click", () => void showPreviewTab("markdown"));
  byId("preview-pdf-tab").addEventListener("click", () => void showPreviewTab("pdf"));
  byId("close-preview").addEventListener("click", resetPreview);
  byId("open-result-folder").addEventListener("click", () => void openResultFolder());
  byId("export-result").addEventListener("click", () => void exportResult());
  byId("settings-button").addEventListener("click", () => byId("settings-dialog").showModal());
  byId("language-select").addEventListener("change", async (event) => {
    state.locale = event.target.value === "es" ? "es" : "en";
    persistent.setItem("sami.locale", state.locale);
    await i18next.changeLanguage(state.locale);
    await window.sami.setLocale(state.locale);
    applyLanguage();
  });
  byId("theme-select").addEventListener("change", (event) => applyTheme(event.target.value));
  byId("markdown-preview").addEventListener("click", (event) => {
    const anchor = event.target.closest("a");
    if (!anchor) return;
    event.preventDefault();
    const destination = anchor.getAttribute("href");
    if (/^https?:/i.test(destination)) {
      void window.sami.openExternal(anchor.href).catch(() => showToast("toast.operationFailed"));
    } else if (destination?.startsWith("#") && destination.length > 1) {
      const id = destination.slice(1);
      const targets = byId("markdown-preview").querySelectorAll("[id]");
      [...targets].find(target => target.id === id)?.scrollIntoView();
    } else if (anchor.dataset.samiMissingLink) {
      showToast("results.linkMissing");
    }
  });
  byId("results-view").addEventListener("dragstart", (event) => {
    const button = event.target.closest("#drag-result");
    if (!button || !state.currentResult?.output_paths?.[0]) {
      event.preventDefault();
      return;
    }
    void dragResult();
  });

  window.sami.onEvent(onRunnerEvent);
  window.sami.onDiagnostic(handleDiagnostic);
  window.sami.onActivity(handleActivity);
  window.sami.onState((value) => {
    handleState(value);
    recoverRunAfterCrash(value);
  });
}

function tick() {
  if (!state.operation) return;
  if (!state.lastEventAt) state.lastEventAt = Date.now();
  const silence = Date.now() - state.lastEventAt;
  state.waiting = silence >= 30_000;
  renderRunState({ waiting: state.waiting, silenceMs: silence });
}

function recoverRunAfterCrash(value) {
  if (state.operation !== "conversion" || !value?.error || !["failed", "cancelled"].includes(value.phase)) return;
  state.operation = null;
  state.cancelling = false;
  const message = value.error.message || t("results.error");
  appendDiagnostic({ message, level: "error" });
  updateControls();
  renderResults({ error: { message }, exit_code: value.phase === "cancelled" ? 130 : 1 });
  showScreen("results");
}

async function bootstrap() {
  applyTheme(state.theme);
  bindEvents();
  byId("mode-select").value = "balanced";
  await i18next.changeLanguage(state.locale);
  applyLanguage();
  updateOutputPath();
  renderSelection();
  renderRunState();
  document.documentElement.dataset.samiReady = "true";
  await window.sami.setLocale(state.locale);
  await refreshHealth();
  setInterval(tick, 1000);
}

void bootstrap().catch((error) => {
  showError(error.message || t("health.noCli"));
});
