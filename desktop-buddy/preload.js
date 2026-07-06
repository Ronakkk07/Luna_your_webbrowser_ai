// Safe bridge between the renderer (character UI) and the main process.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("buddy", {
  // Toggle whether the overlay captures the mouse (true only over the character).
  setInteractive: (interactive) => ipcRenderer.send("set-interactive", interactive),
  // Open a URL in the default browser.
  openExternal: (url) => ipcRenderer.send("open-external", url),
  // Read config.json (login + server URL) from the main process.
  getConfig: () => ipcRenderer.invoke("get-config"),
  // Fired by the global hotkey (Ctrl+Alt+L) to summon Luna.
  onSummon: (cb) => ipcRenderer.on("summon", () => cb()),
});
