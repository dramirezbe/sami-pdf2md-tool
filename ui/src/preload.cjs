const { contextBridge, ipcRenderer, webUtils } = require("electron");

const dropped = new Set();
const invoke = name => (...args) => ipcRenderer.invoke(`sami:${name}`, ...args);
const subscribe = name => callback => {
  const handler = (_event, value) => callback(value);
  ipcRenderer.on(`sami:${name}`, handler);
  return () => ipcRenderer.removeListener(`sami:${name}`, handler);
};

contextBridge.exposeInMainWorld("sami", {
  getHealth: invoke("health"),
  setup: invoke("setup"),
  repairInstallation: invoke("repair"),
  selectFiles: invoke("files"),
  selectFolder: invoke("folder"),
  selectOutput: invoke("output"),
  dropPaths(files) {
    dropped.clear();
    for (const file of files) {
      const path = webUtils.getPathForFile(file);
      if (path) dropped.add(path);
    }
    return [...dropped];
  },
  addDroppedPaths(paths) {
    const approved = paths.filter(path => dropped.has(path));
    dropped.clear();
    return invoke("drop")(approved);
  },
  startConversion: invoke("start"),
  cancelConversion: invoke("cancel"),
  loadPreview: invoke("preview"),
  openOutputFolder: invoke("show-output"),
  exportResult: invoke("export"),
  startResultDrag: invoke("drag"),
  openExternal: invoke("open-external"),
  setLocale: invoke("locale"),
  onEvent: subscribe("event"),
  onDiagnostic: subscribe("diagnostic"),
  onActivity: subscribe("activity"),
  onState: subscribe("state"),
});
