import { app, BrowserWindow, Menu, dialog, ipcMain, nativeImage, net, protocol, session, shell } from "electron";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { setTimeout as wait } from "node:timers/promises";
import { CliRunner } from "./cli-runner.js";
import { Documents } from "./documents.js";

const APPLICATION = "sami-app://app";
const INDEX = `${APPLICATION}/index.html`;
const CLI_RELEASE = "https://github.com/dramirezbe/sami-pdf2md-tool/releases/tag/v0.3.1";
const source = dirname(fileURLToPath(import.meta.url));
const renderer = join(source, "..", "dist");
const icon = join(renderer, "assets", "icons", "sami-icon-128.png");
const contentPolicy = [
  "default-src 'none'", "script-src 'self' 'wasm-unsafe-eval'", "style-src 'self' 'unsafe-inline'",
  "img-src 'self' sami-doc: data: blob:", "connect-src 'self' sami-doc: blob:",
  "font-src 'self' data: blob:", "worker-src 'self' blob:", "base-uri 'none'", "form-action 'none'",
].join("; ");

protocol.registerSchemesAsPrivileged([
  { scheme: "sami-app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
  { scheme: "sami-doc", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } },
]);

const messages = {
  en: {
    choosePdf: "Choose PDFs", chooseFolder: "Choose a folder", chooseOutput: "Choose an output folder",
    chooseExport: "Choose where to copy the result", closeTitle: "SAMI is working",
    closeMessage: "Finish this task or cancel it before closing SAMI.",
    keepWorking: "Keep working", cancelClose: "Cancel and close",
  },
  es: {
    choosePdf: "Elige los PDF", chooseFolder: "Elige una carpeta", chooseOutput: "Elige la carpeta de salida",
    chooseExport: "Elige dónde copiar el resultado", closeTitle: "SAMI está trabajando",
    closeMessage: "Espera a que termine esta tarea o cancélala antes de cerrar SAMI.",
    keepWorking: "Seguir trabajando", cancelClose: "Cancelar y cerrar",
  },
};

const documents = new Documents();
const runner = new CliRunner();
let window;
let locale = "en";
let operation = null;
let closing = false;
let confirmedClose = false;

function publish(type, value) {
  if (window && !window.isDestroyed()) window.webContents.send(`sami:${type}`, value);
}

runner.on("event", event => {
  documents.addEvent(event);
  publish("event", event);
});
for (const type of ["activity", "diagnostic", "state"]) {
  runner.on(type, value => publish(type, value));
}

function registerHandlers() {
  function handle(name, handler) {
    ipcMain.handle(`sami:${name}`, (event, ...args) => {
      if (event.sender !== window?.webContents || event.senderFrame?.url !== INDEX) {
        throw new Error("This operation requires the SAMI application window.");
      }
      return handler(...args);
    });
  }

  async function choose(title, properties, filters) {
    const result = await dialog.showOpenDialog(window, { title: messages[locale][title], properties, filters });
    return result.canceled ? [] : result.filePaths;
  }

  handle("health", () => runner.health());
  handle("repair", () => shell.openExternal(CLI_RELEASE));
  handle("setup", async () => {
    if (operation) throw new Error("SAMI is already working.");
    operation = "setup";
    try {
      return await runner.setup();
    } finally {
      operation = null;
    }
  });
  handle("files", async () => documents.selectInputs(await choose(
    "choosePdf", ["openFile", "multiSelections"], [{ name: "PDF", extensions: ["pdf"] }],
  )));
  handle("folder", async () => documents.selectInputs(await choose("chooseFolder", ["openDirectory"])));
  handle("output", async () => {
    const [folder] = await choose("chooseOutput", ["openDirectory", "createDirectory"]);
    return folder ? documents.selectOutput(folder) : null;
  });
  handle("drop", paths => documents.selectInputs(paths));
  handle("start", async options => {
    if (operation) throw new Error("SAMI is already working.");
    const request = documents.validateRequest(options);
    operation = "conversion";
    documents.beginRun(request);
    try {
      const { completion } = await runner.start(request);
      completion.catch(error => publish("diagnostic", { message: error.message, level: "error" }))
        .finally(() => { operation = null; });
      return { started: true };
    } catch (error) {
      operation = null;
      throw error;
    }
  });
  handle("cancel", async () => { await runner.cancel(); });
  handle("preview", request => documents.loadPreview(request));
  handle("show-output", async markdown => {
    const error = await shell.openPath(dirname(documents.result(markdown).markdown));
    if (error) throw new Error(error);
  });
  handle("export", async markdown => {
    documents.result(markdown);
    const [target] = await choose("chooseExport", ["openDirectory", "createDirectory"]);
    return target ? documents.exportResult(markdown, target) : null;
  });
  handle("drag", async markdown => {
    const files = await documents.dragPaths(markdown);
    const dragIcon = nativeImage.createFromPath(icon).resize({ width: 32 });
    window.webContents.startDrag(files.length === 1 ? { file: files[0], icon: dragIcon } : { files, icon: dragIcon });
  });
  handle("open-external", link => {
    const url = new URL(link);
    if (!["https:", "http:"].includes(url.protocol)) throw new Error("This link cannot be opened.");
    return shell.openExternal(url.href);
  });
  handle("locale", language => {
    locale = language === "es" ? "es" : "en";
  });
}

function registerProtocols() {
  protocol.handle("sami-app", async request => {
    const url = new URL(request.url);
    if (url.hostname !== "app") return new Response(null, { status: 404 });
    const target = resolve(renderer, `.${decodeURIComponent(url.pathname)}`);
    const path = relative(renderer, target);
    if (!path || path === ".." || path.startsWith(`..${sep}`) || isAbsolute(path)) {
      return new Response(null, { status: 404 });
    }
    try {
      const response = await net.fetch(pathToFileURL(target).href);
      if (target !== join(renderer, "index.html")) return response;
      const headers = new Headers(response.headers);
      headers.set("Content-Security-Policy", contentPolicy);
      return new Response(response.body, { status: response.status, headers });
    } catch {
      return new Response(null, { status: 404 });
    }
  });
  protocol.handle("sami-doc", async request => {
    const entry = documents.previewResource(request.url);
    if (!entry || request.method !== "GET") return new Response(null, { status: 404 });
    try {
      const response = await net.fetch(pathToFileURL(entry.file).href);
      const headers = new Headers(response.headers);
      headers.set("Content-Type", entry.type);
      headers.set("X-Content-Type-Options", "nosniff");
      headers.set("Content-Security-Policy", "default-src 'none'");
      headers.set("Access-Control-Allow-Origin", APPLICATION);
      headers.set("Cache-Control", "no-store");
      return new Response(response.body, { status: response.status, headers });
    } catch {
      return new Response(null, { status: 404 });
    }
  });
}

function createWindow({ smoke = false } = {}) {
  const current = new BrowserWindow({
    width: 1160, height: 850, minWidth: 720, minHeight: 560,
    icon, show: false,
    webPreferences: {
      preload: join(source, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  current.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  current.webContents.on("will-navigate", event => event.preventDefault());
  current.webContents.on("will-attach-webview", event => event.preventDefault());
  if (!smoke) current.once("ready-to-show", () => current.show());
  current.on("close", event => {
    if (!operation || confirmedClose) return;
    event.preventDefault();
    if (closing) return;
    closing = true;
    const text = messages[locale];
    void dialog.showMessageBox(current, {
      type: "question", title: text.closeTitle, message: text.closeMessage,
      buttons: [text.keepWorking, text.cancelClose], defaultId: 0, cancelId: 0,
    }).then(async ({ response }) => {
      if (response === 1) {
        await runner.shutdown();
        confirmedClose = true;
        current.close();
      }
    }).catch(error => publish("diagnostic", { message: error.message, level: "error" }))
      .finally(() => { closing = false; });
  });
  current.on("closed", () => { if (window === current) window = null; });
  return current;
}

async function launchWindow({ smoke = false } = {}) {
  window = createWindow({ smoke });
  await window.loadURL(INDEX);
  if (!smoke) return;
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const loaded = await window.webContents.executeJavaScript("document.documentElement.dataset.samiReady === 'true'");
    if (loaded) return app.exit(0);
    await wait(100);
  }
  console.error("The SAMI renderer did not initialize.");
  app.exit(1);
}

const smoke = process.argv.includes("--smoke-test");
app.setAppUserModelId("com.dramirezbe.sami");
app.whenReady().then(async () => {
  locale = app.getLocale().startsWith("es") ? "es" : "en";
  Menu.setApplicationMenu(null);
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.on("will-download", event => event.preventDefault());
  registerProtocols();
  registerHandlers();
  await launchWindow({ smoke });
}).catch(error => {
  console.error(error);
  app.exit(1);
});

app.on("activate", () => {
  if (!window) void launchWindow();
});
app.on("before-quit", event => {
  if (operation && !confirmedClose) {
    event.preventDefault();
    window?.close();
  }
});
app.on("window-all-closed", () => { if (process.platform !== "darwin" || confirmedClose) app.quit(); });
