// Luna Desktop Buddy — Electron main process.
//
// Creates a full-screen, transparent, always-on-top overlay window that the
// character is drawn onto. The overlay is click-through everywhere EXCEPT over
// the buddy (the renderer toggles that as the pointer enters/leaves the sprite),
// so it never blocks your normal desktop use.

const { app, BrowserWindow, ipcMain, shell, globalShortcut, screen } = require("electron");
const path = require("path");
const fs = require("fs");

let win;

function createWindow() {
  const { bounds } = screen.getPrimaryDisplay();

  win = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    transparent: true,
    frame: false,
    resizable: false,
    movable: false,
    skipTaskbar: true,
    hasShadow: false,
    fullscreenable: false,
    // Not focusable so clicking the buddy never steals focus from your work.
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      // Allow the renderer to fetch the local Vosk model file (file://) and run
      // the WASM engine. This is a local, self-contained app.
      webSecurity: false,
      backgroundThrottling: false,
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  // Start fully click-through; the renderer turns this off while the pointer is
  // over the buddy so only the character is interactive.
  win.setIgnoreMouseEvents(true, { forward: true });

  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  // Live from PC boot: register to launch at login (only once packaged, so we
  // never auto-start the dev `electron` binary).
  if (app.isPackaged) {
    app.setLoginItemSettings({ openAtLogin: true });
  }

  createWindow();

  // Global hotkey to summon Luna (a reliable trigger alongside the wake word).
  globalShortcut.register("Control+Alt+L", () => {
    win && win.webContents.send("summon");
  });

  // Debug: toggle DevTools for the overlay (the window isn't focusable, so a
  // global shortcut is the reliable way in).
  globalShortcut.register("Control+Alt+D", () => {
    if (!win) return;
    const wc = win.webContents;
    if (wc.isDevToolsOpened()) wc.closeDevTools();
    else wc.openDevTools({ mode: "detach" });
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// ---- IPC from the renderer ----

// Only the character/dialog should capture the mouse; everything else passes
// through to the apps behind the overlay.
ipcMain.on("set-interactive", (_e, interactive) => {
  if (!win) return;
  if (interactive) win.setIgnoreMouseEvents(false);
  else win.setIgnoreMouseEvents(true, { forward: true });
});

// Read config.json in the main process (renderer fetch() can't read file:// URLs).
// Prefer a user-editable copy in the app's userData folder (so it survives
// updates and can be edited after install); fall back to the bundled dev copy.
function configPath() {
  const userCopy = path.join(app.getPath("userData"), "config.json");
  if (fs.existsSync(userCopy)) return userCopy;
  return path.join(__dirname, "config.json");
}

ipcMain.handle("get-config", () => {
  const file = configPath();
  try {
    const cfg = JSON.parse(fs.readFileSync(file, "utf-8"));
    console.log("Loaded config from", file);
    return cfg;
  } catch (err) {
    console.warn("Could not read config at", file, "-", err.message);
    return null;
  }
});

// Buddy asks the OS to open a URL in the default browser (for web commands).
ipcMain.on("open-external", (_e, url) => {
  if (typeof url === "string" && /^https?:\/\//.test(url)) shell.openExternal(url);
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("will-quit", () => globalShortcut.unregisterAll());
