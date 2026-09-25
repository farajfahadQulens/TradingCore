const BASE_URL = "http://192.168.1.X:8000"
const API = BASE_URL + "/api/v1"

async function get(path) {
  const req = new Request(API + path)
  req.allowInsecureRequest = true
  req.timeoutInterval = 8
  const resp = await req.loadString()
  if (!resp) throw new Error("empty response")
  try {
    return JSON.parse(resp)
  } catch (_) {
    throw new Error("bad response: " + resp.slice(0, 60))
  }
}

function money(v) {
  return Number(v).toFixed(2)
}

async function run() {
  const data = await get("/accounts/balance")
  const bal = data.balance

  const widget = new ListWidget()

  const equity = widget.addText(`NOK ${money(bal.balance)}`)
  equity.font = Font.boldSystemFont(20)
  equity.textColor = Color.white()

  widget.addSpacer(2)

  const pnl = bal.profitLoss || 0
  const pnlLine = widget.addText(`${pnl >= 0 ? "+" : ""}${money(pnl)}`)
  pnlLine.font = Font.boldSystemFont(13)
  pnlLine.textColor = pnl >= 0 ? new Color("#2ecc71") : new Color("#ff5c5c")

  widget.addSpacer(4)

  const availLine = widget.addText(`${money(bal.available)} available`)
  availLine.font = Font.systemFont(9)
  availLine.textColor = new Color("#999999")

  widget.addSpacer(2)

  const depositLine = widget.addText(`${money(bal.deposit)} deposited`)
  depositLine.font = Font.systemFont(9)
  depositLine.textColor = new Color("#666666")

  widget.addSpacer(4)

  const now = new Date()
  const time = widget.addText(
    `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`
  )
  time.font = Font.systemFont(8)
  time.textColor = new Color("#555555")

  Script.setWidget(widget)
  Script.complete()
}

try {
  await run()
} catch (e) {
  const widget = new ListWidget()
  const err = widget.addText("OFFLINE")
  err.font = Font.boldSystemFont(14)
  err.textColor = new Color("#ff5c5c")
  widget.addSpacer(2)
  const msg = widget.addText(String(e.message).slice(0, 50))
  msg.font = Font.systemFont(8)
  msg.textColor = new Color("#888888")
  Script.setWidget(widget)
  Script.complete()
}
