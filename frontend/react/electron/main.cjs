const { app, BrowserWindow } = require("electron");
const path = require("path");

const DEV_SERVER_URL = process.env.ELECTRON_RENDERER_URL || "http://localhost:5173";

function createWindow() {
    const win = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    if (app.isPackaged) {
        win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
        return;
    }
    win.loadURL(DEV_SERVER_URL);
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
        app.quit();
    }
});