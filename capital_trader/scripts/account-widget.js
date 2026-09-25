const BASE_URL = "http://192.168.1.X:8000"

async function run() {
  const api = BASE_URL + "/api/v1"

  const [balanceData, posData] = await Promise.all([
    new Request(api + "/accounts/balance").loadJSON(),
    new Request(api + "/positions").loadJSON(),
  ])

  const bal = balanceData.balance
  const positions = posData.positions || []

  const widget = new ListWidget()
  widget.backgroundColor = new Color("#0b0f17")

  const balLine = widget.addText(`NOK ${bal.balance.toFixed(2)}`)
  balLine.textColor = Color.white()
  balLine.font = Font.boldSystemFont(20)

  widget.addSpacer(2)

  const pl = bal.profitLoss
  const plColor = pl >= 0 ? new Color("#2ecc9a") : new Color("#e85555")
  const plLine = widget.addText(`${pl >= 0 ? "+" : ""}NOK ${pl.toFixed(2)}`)
  plLine.textColor = plColor
  plLine.font = Font.systemFont(13)

  const availLine = widget.addText(`Available  NOK ${bal.available.toFixed(2)}`)
  availLine.textColor = new Color("#8b95a8")
  availLine.font = Font.systemFont(11)

  if (positions.length > 0) {
    widget.addSpacer(6)

    const sep = widget.addText("── Positions ──")
    sep.textColor = new Color("#3a4252")
    sep.font = Font.systemFont(10)
    sep.textOpacity = 0.6

    widget.addSpacer(4)

    for (const item of positions) {
      const p = item.position
      const m = item.market
      const dirColor = p.direction === "BUY" ? new Color("#2ecc9a") : new Color("#e85555")
      const line = widget.addText(`${m.epic}  ${p.direction}  ${p.size} @ ${p.level}`)
      line.textColor = dirColor
      line.font = Font.monospacedSystemFont(12, 12)
    }
  } else {
    widget.addSpacer(6)
    const empty = widget.addText("No open positions")
    empty.textColor = new Color("#3a4252")
    empty.font = Font.systemFont(11)
  }

  widget.addSpacer(4)
  const now = new Date()
  const ts = widget.addText(`Updated  ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`)
  ts.textColor = new Color("#3a4252")
  ts.font = Font.systemFont(9)
  ts.textOpacity = 0.5

  Script.setWidget(widget)
  widget.presentMedium()
}

try {
  await run()
} catch (e) {
  const err = new ListWidget()
  err.backgroundColor = new Color("#0b0f17")
  const msg = err.addText(`Error: ${e.message}`)
  msg.textColor = new Color("#e85555")
  msg.font = Font.systemFont(12)
  Script.setWidget(err)
  err.presentMedium()
}
