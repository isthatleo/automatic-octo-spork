// Billion desktop shell -- a native window around the local control room.
// Expects the stack to be running (docker compose up -d, ports 3005/8000).
// If the frontend isn't up yet, shows a reactor-styled waiting screen that
// retries automatically instead of a white error page.
const { app, BrowserWindow, shell } = require('electron')

const FRONTEND_URL = process.env.BILLION_FRONTEND_URL || 'http://localhost:3005'
const RETRY_MS = 2500

const WAITING_HTML = `data:text/html;charset=utf-8,` + encodeURIComponent(`<!doctype html>
<html><head><meta charset="utf-8"><title>Billion</title><style>
  body{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
       background:#05080e;color:#e2e8f0;font-family:ui-monospace,Consolas,monospace}
  .ring{width:110px;height:110px;border-radius:50%;border:2px solid rgba(64,224,255,.25);
        border-top-color:#40e0ff;animation:spin 1.6s linear infinite;
        box-shadow:0 0 40px rgba(64,224,255,.25), inset 0 0 30px rgba(64,224,255,.12)}
  @keyframes spin{to{transform:rotate(360deg)}}
  h1{font-size:15px;letter-spacing:4px;color:#40e0ff;margin:26px 0 6px}
  p{font-size:11px;color:#64748b;margin:2px}
</style></head><body>
  <div class="ring"></div><h1>B I L L I O N</h1>
  <p>Waiting for the control room at ${FRONTEND_URL}…</p>
  <p>Start the stack: <b>cd nancy-billion && docker compose up -d</b></p>
</body></html>`)

async function frontendUp() {
  try {
    const res = await fetch(FRONTEND_URL, { signal: AbortSignal.timeout(1500) })
    return res.ok || res.status < 500
  } catch {
    return false
  }
}

async function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    backgroundColor: '#05080e',
    autoHideMenuBar: true,
    title: 'Billion',
    webPreferences: { contextIsolation: true },
  })

  // External links open in the real browser, not inside the shell.
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  const load = async () => {
    if (await frontendUp()) {
      win.loadURL(FRONTEND_URL)
    } else {
      win.loadURL(WAITING_HTML)
      const timer = setInterval(async () => {
        if (await frontendUp()) {
          clearInterval(timer)
          win.loadURL(FRONTEND_URL)
        }
      }, RETRY_MS)
      win.on('closed', () => clearInterval(timer))
    }
  }
  await load()
}

app.whenReady().then(createWindow)
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
