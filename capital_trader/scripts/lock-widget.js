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
  const widget = new ListWidget()

  const [balanceData, posData] = await Promise.all([
    get("/accounts/balance"),
    get("/positions"),
  ])

  const bal = balanceData.balance
  const positions = posData.positions || []

  const equity = widget.addText(`NOK ${money(bal.balance)}`)
  equity.font = Font.boldSystemFont(18)
  equity.textColor = Color.white()

  widget.addSpacer(2)

  const pnl = bal.profitLoss || 0
  const pnlLine = widget.addText(`${pnl >= 0 ? "\u25b2" : "\u25bc"} ${money(Math.abs(pnl))}`)
  pnlLine.font = Font.boldSystemFont(11)
  pnlLine.textColor = pnl >= 0 ? new Color("#2ecc71") : new Color("#ff5c5c")

  widget.addSpacer(4)

  if (positions.length > 0) {
    const item = positions[0]
    const p = item.position
    const m = item.market
    const dir = p.direction === "BUY" ? "LONG" : "SHORT"
    const pos = widget.addText(`${m.epic} ${dir}`)
    pos.font = Font.boldSystemFont(10)
    pos.textColor = p.direction === "BUY" ? new Color("#2ecc71") : new Color("#ff5c5c")
  } else {
    const empty = widget.addText("NO POSITIONS")
    empty.font = Font.boldSystemFont(10)
    empty.textColor = new Color("#888888")
  }

  widget.addSpacer(3)

  const now = new Date()
  const time = widget.addText(`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`)
  time.font = Font.systemFont(8)
  time.textColor = new Color("#666666")

  Script.setWidget(widget)
  Script.complete()
}

try {
  await run()
} catch (e) {
  const widget = new ListWidget()
  const err = widget.addText("MARKET OFFLINE")
  err.font = Font.boldSystemFont(12)
  err.textColor = new Color("#ff5c5c")
  widget.addSpacer(2)
  const msg = widget.addText(String(e.message).slice(0, 60))
  msg.font = Font.systemFont(8)
  msg.textColor = new Color("#999999")
  Script.setWidget(widget)
  Script.complete()
}
