const state = {
  sessionId: null,
}

const GOLD_CANDLES_URL = "/api/gold/candles.csv"
const GOLD_HISTORY_MINUTES = 10000
const GOLD_INTERVALS = { "1m": 1, "5m": 5, "15m": 15 }
const GOLD_REFRESH_MS = 60000
let goldChart = null
let goldCandleSeries = null
let goldLineSeries = null
let goldVolumeSeries = null
let goldRawCandles = []
let goldVisibleCandles = []
let goldVisibleCandleMap = new Map()
let goldSelectedInterval = "1m"
let goldSelectedRange = 60
let goldChartType = "candles"
let goldChartLoadToken = 0
let goldChartInitialFit = false

const els = {
  equity: document.getElementById("equity"),
  available: document.getElementById("available"),
  profitLoss: document.getElementById("profitLoss"),
  deposit: document.getElementById("deposit"),
  exposure: document.getElementById("exposure"),
  positionCount: document.getElementById("positionCount"),
  writes: document.getElementById("writes"),
  tradeMode: document.getElementById("tradeMode"),
  capitalHealth: document.getElementById("capitalHealth"),
  broker: document.getElementById("broker"),
  ticketCount: document.getElementById("ticketCount"),
  ticketBreakdown: document.getElementById("ticketBreakdown"),
  stackStatus: document.getElementById("stackStatus"),
  marketStatus: document.getElementById("marketStatus"),
  reconciliation: document.getElementById("reconciliation"),
  telegramStatus: document.getElementById("telegramStatus"),
  mode: document.getElementById("mode"),
  modeSelect: document.getElementById("modeSelect"),
  positions: document.getElementById("positions"),
  tickets: document.getElementById("tickets"),
  actions: document.getElementById("actions"),
  tradeLogs: document.getElementById("tradeLogs"),
  healthGrid: document.getElementById("healthGrid"),
  notifications: document.getElementById("notifications"),
  alertForm: document.getElementById("alertForm"),
  alertType: document.getElementById("alertType"),
  alertEpic: document.getElementById("alertEpic"),
  alertCondition: document.getElementById("alertCondition"),
  alertThreshold: document.getElementById("alertThreshold"),
  alertCooldown: document.getElementById("alertCooldown"),
  alertRecovery: document.getElementById("alertRecovery"),
  presetAlerts: document.getElementById("presetAlerts"),
  evaluateAlerts: document.getElementById("evaluateAlerts"),
  memories: document.getElementById("memories"),
  browserSnapshots: document.getElementById("browserSnapshots"),
  canvasConnect: document.getElementById("canvasConnect"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  chatLog: document.getElementById("chatLog"),
  refreshButton: document.getElementById("refreshButton"),
  systemTime: document.getElementById("systemTime"),
  goldPanel: document.getElementById("goldPanel"),
  goldChart: document.getElementById("goldChart"),
  goldChartState: document.getElementById("goldChartState"),
  goldChartStatus: document.getElementById("goldChartStatus"),
  goldCandleDownload: document.getElementById("goldCandleDownload"),
  goldLastPrice: document.getElementById("goldLastPrice"),
  goldCandleChange: document.getElementById("goldCandleChange"),
  goldLegendTime: document.getElementById("goldLegendTime"),
  goldLegendOpen: document.getElementById("goldLegendOpen"),
  goldLegendHigh: document.getElementById("goldLegendHigh"),
  goldLegendLow: document.getElementById("goldLegendLow"),
  goldLegendClose: document.getElementById("goldLegendClose"),
  goldLegendVolume: document.getElementById("goldLegendVolume"),
  goldFitButton: document.getElementById("goldFitButton"),
  goldFullscreenButton: document.getElementById("goldFullscreenButton"),
  goldTypeButtons: document.querySelectorAll("[data-gold-type]"),
  goldIntervalButtons: document.querySelectorAll("[data-gold-interval]"),
  goldRangeButtons: document.querySelectorAll("[data-gold-range]"),
}

function money(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return "--"
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(number)
}

function compactNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return "--"
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(number)
}

function text(value, fallback = "--") {
  if (value === null || value === undefined || value === "") return fallback
  return String(value)
}

function midpoint(bid, ask) {
  const bidValue = Number(bid)
  const askValue = Number(ask)
  if (!Number.isFinite(bidValue) || !Number.isFinite(askValue)) return null
  return (bidValue + askValue) / 2
}

function parseCsvRows(csv) {
  const lines = String(csv || "").trim().split(/\r?\n/).filter(Boolean)
  if (lines.length < 2) return []
  const headers = lines.shift().split(",")
  headers[0] = headers[0].replace(/^\uFEFF/, "")
  return lines.map((line) => {
    const values = line.split(",")
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]))
  })
}

function storedGoldCandle(row) {
  const candle = {
    time: Number(row.timestamp),
    open: midpoint(row.open_bid, row.open_ask),
    high: midpoint(row.high_bid, row.high_ask),
    low: midpoint(row.low_bid, row.low_ask),
    close: midpoint(row.close_bid, row.close_ask),
    volume: Number(row.volume),
  }
  return Object.values(candle).every((value) => typeof value === "number" && Number.isFinite(value)) ? candle : null
}

function normalizeGoldCandles(rows) {
  const byTime = new Map()
  rows.map(storedGoldCandle).filter(Boolean).forEach((candle) => byTime.set(candle.time, candle))
  return [...byTime.values()].sort((left, right) => left.time - right.time)
}

function aggregateGoldCandles(candles, intervalMinutes) {
  if (intervalMinutes === 1) return candles
  const bucketSeconds = intervalMinutes * 60
  const aggregated = []
  candles.forEach((candle) => {
    const time = Math.floor(candle.time / bucketSeconds) * bucketSeconds
    const current = aggregated[aggregated.length - 1]
    if (!current || current.time !== time) {
      aggregated.push({ ...candle, time })
      return
    }
    current.high = Math.max(current.high, candle.high)
    current.low = Math.min(current.low, candle.low)
    current.close = candle.close
    current.volume += candle.volume
  })
  return aggregated
}

function goldViewCandles() {
  return aggregateGoldCandles(goldRawCandles, GOLD_INTERVALS[goldSelectedInterval])
}

function syncGoldToolbar() {
  const groups = [
    [els.goldTypeButtons, "goldType", goldChartType],
    [els.goldIntervalButtons, "goldInterval", goldSelectedInterval],
    [els.goldRangeButtons, "goldRange", goldSelectedRange],
  ]
  groups.forEach(([buttons, key, value]) => {
    buttons.forEach((button) => {
      const active = button.dataset[key] === String(value)
      button.classList.toggle("active", active)
      button.setAttribute("aria-pressed", String(active))
    })
  })
}

function resetGoldLegend() {
  els.goldLegendTime.textContent = "--"
  els.goldLegendOpen.textContent = "--"
  els.goldLegendHigh.textContent = "--"
  els.goldLegendLow.textContent = "--"
  els.goldLegendClose.textContent = "--"
  els.goldLegendVolume.textContent = "--"
  for (const element of [els.goldLegendOpen, els.goldLegendHigh, els.goldLegendLow, els.goldLegendClose]) {
    element.className = ""
  }
}

function renderGoldLegend(candle) {
  if (!candle) {
    resetGoldLegend()
    return
  }
  const timestamp = new Date(candle.time * 1000)
  els.goldLegendTime.textContent = timestamp.toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
  els.goldLegendOpen.textContent = money(candle.open)
  els.goldLegendHigh.textContent = money(candle.high)
  els.goldLegendLow.textContent = money(candle.low)
  els.goldLegendClose.textContent = money(candle.close)
  els.goldLegendVolume.textContent = compactNumber(candle.volume)
  const color = candle.close >= candle.open ? "positive" : "negative"
  for (const element of [els.goldLegendOpen, els.goldLegendHigh, els.goldLegendLow, els.goldLegendClose]) {
    element.className = color
  }
}

function applyGoldRange() {
  if (!goldChart || goldVisibleCandles.length === 0) return
  if (goldSelectedRange === "max") {
    goldChart.timeScale().fitContent()
    return
  }
  const intervalMinutes = GOLD_INTERVALS[goldSelectedInterval]
  const visibleBars = Math.max(1, Math.ceil(goldSelectedRange / intervalMinutes))
  const padding = Math.max(2, Math.ceil(visibleBars * 0.05))
  goldChart.timeScale().setVisibleLogicalRange({
    from: Math.max(0, goldVisibleCandles.length - visibleBars),
    to: goldVisibleCandles.length + padding,
  })
}

function renderGoldCandles(candles, resetRange = false) {
  goldVisibleCandles = candles
  goldVisibleCandleMap = new Map(candles.map((candle) => [candle.time, candle]))
  goldCandleSeries.setData(candles)
  goldLineSeries.setData(candles.map((candle) => ({ time: candle.time, value: candle.close })))
  goldVolumeSeries.setData(
    candles.map((candle) => ({
      time: candle.time,
      value: candle.volume,
      color: candle.close >= candle.open ? "rgba(38, 166, 154, .36)" : "rgba(239, 83, 80, .36)",
    })),
  )
  goldCandleSeries.applyOptions({ visible: goldChartType === "candles" })
  goldLineSeries.applyOptions({ visible: goldChartType === "line" })
  if (!goldChartInitialFit || resetRange) {
    applyGoldRange()
    goldChartInitialFit = true
  }
  const latest = candles[candles.length - 1]
  const previous = candles[candles.length - 2] || latest
  const change = latest.close - previous.close
  const percent = previous.close === 0 ? 0 : (change / previous.close) * 100
  const synced = new Date().toLocaleTimeString([], { hour12: false })
  els.goldLastPrice.textContent = money(latest.close)
  els.goldCandleChange.textContent = `${change >= 0 ? "+" : ""}${money(change)} (${percent >= 0 ? "+" : ""}${percent.toFixed(2)}%)`
  els.goldCandleChange.className = change >= 0 ? "positive" : "negative"
  els.goldChartStatus.textContent = `${candles.length} bars · ${goldSelectedInterval} · synced ${synced}`
  els.goldChartStatus.removeAttribute("title")
  els.goldChartState.dataset.state = "live"
  els.goldChart.setAttribute("aria-label", `GOLD ${goldChartType} chart, ${goldSelectedInterval} interval, ${candles.length} bars`)
  renderGoldLegend(latest)
}

function resetGoldChartData() {
  goldRawCandles = []
  goldVisibleCandles = []
  goldVisibleCandleMap = new Map()
  goldCandleSeries.setData([])
  goldLineSeries.setData([])
  goldVolumeSeries.setData([])
  els.goldLastPrice.textContent = "--"
  els.goldCandleChange.textContent = "--"
  els.goldCandleChange.className = ""
  resetGoldLegend()
}

function renderGoldCrosshair(parameter) {
  const latest = goldVisibleCandles[goldVisibleCandles.length - 1]
  const candle = parameter.time && parameter.point ? goldVisibleCandleMap.get(parameter.time) : latest
  renderGoldLegend(candle || latest)
}

function initGoldChart() {
  if (typeof LightweightCharts === "undefined") {
    els.goldChartStatus.textContent = "CHART LIB UNAVAILABLE"
    els.goldChartState.dataset.state = "error"
    return false
  }
  const bounds = els.goldChart.getBoundingClientRect()
  try {
    goldChart = LightweightCharts.createChart(els.goldChart, {
      width: Math.max(1, Math.floor(bounds.width)),
      height: Math.max(1, Math.floor(bounds.height)),
      layout: {
        background: { type: "solid", color: "#0b0e11" },
        textColor: "#787b86",
        fontSize: 11,
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      },
      localization: {
        priceFormatter: (price) => money(price),
      },
      grid: {
        vertLines: { color: "rgba(120, 123, 134, .09)" },
        horzLines: { color: "rgba(120, 123, 134, .09)" },
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: {
          color: "rgba(120, 123, 134, .55)",
          width: 1,
          style: LightweightCharts.LineStyle.Dashed,
          labelBackgroundColor: "#363a45",
        },
        horzLine: {
          color: "rgba(120, 123, 134, .55)",
          width: 1,
          style: LightweightCharts.LineStyle.Dashed,
          labelBackgroundColor: "#363a45",
        },
      },
      rightPriceScale: {
        borderColor: "#2a2e39",
        minimumWidth: 78,
        scaleMargins: { top: 0.08, bottom: 0.24 },
      },
      timeScale: {
        borderColor: "#2a2e39",
        timeVisible: true,
        secondsVisible: false,
        rightBarStaysOnScroll: true,
        minBarSpacing: 0.05,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    })
    goldCandleSeries = goldChart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderUpColor: "#26a69a",
      borderDownColor: "#ef5350",
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
      priceLineVisible: true,
      lastValueVisible: true,
    })
    goldLineSeries = goldChart.addLineSeries({
      color: "#2962ff",
      lineWidth: 2,
      crosshairMarkerVisible: true,
      priceLineVisible: true,
      lastValueVisible: true,
      visible: false,
    })
    goldVolumeSeries = goldChart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    })
    goldChart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    goldChart.subscribeCrosshairMove(renderGoldCrosshair)
    const resizeObserver = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect
      if (rect.width > 0 && rect.height > 0) goldChart.resize(Math.floor(rect.width), Math.floor(rect.height))
    })
    resizeObserver.observe(els.goldChart)
    return true
  } catch (error) {
    els.goldChartStatus.textContent = "CHART UNAVAILABLE"
    els.goldChartStatus.title = error.message
    els.goldChartState.dataset.state = "error"
    return false
  }
}

async function loadGoldCandles() {
  if (!goldCandleSeries || !goldLineSeries || !goldVolumeSeries) return
  const token = ++goldChartLoadToken
  els.goldChartStatus.textContent = "LOADING"
  els.goldChartState.dataset.state = "live"
  try {
    const start = new Date(Date.now() - GOLD_HISTORY_MINUTES * 60 * 1000).toISOString()
    const params = new URLSearchParams({ limit: String(GOLD_HISTORY_MINUTES), start })
    const url = `${GOLD_CANDLES_URL}?${params}`
    els.goldCandleDownload.href = url
    const response = await fetch(url, { cache: "no-store" })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    goldRawCandles = normalizeGoldCandles(parseCsvRows(await response.text()))
    if (token !== goldChartLoadToken) return
    if (goldRawCandles.length === 0) {
      resetGoldChartData()
      els.goldChartStatus.textContent = "NO CANDLES"
      return
    }
    renderGoldCandles(goldViewCandles())
  } catch (error) {
    if (token !== goldChartLoadToken) return
    resetGoldChartData()
    els.goldChartStatus.textContent = "UNAVAILABLE"
    els.goldChartStatus.title = error.message
    els.goldChartState.dataset.state = "error"
  }
}

function setGoldChartType(type) {
  if (!["candles", "line"].includes(type)) return
  goldChartType = type
  syncGoldToolbar()
  if (goldVisibleCandles.length > 0) renderGoldCandles(goldVisibleCandles)
}

function setGoldInterval(interval) {
  if (!GOLD_INTERVALS[interval]) return
  goldSelectedInterval = interval
  syncGoldToolbar()
  if (goldRawCandles.length > 0) renderGoldCandles(goldViewCandles(), true)
}

function setGoldRange(range) {
  goldSelectedRange = range === "max" ? "max" : Math.max(1, Number(range) || 60)
  syncGoldToolbar()
  applyGoldRange()
}

function syncGoldFullscreen() {
  const active = document.fullscreenElement === els.goldPanel
  els.goldFullscreenButton.textContent = active ? "Exit" : "Expand"
  els.goldFullscreenButton.setAttribute("aria-pressed", String(active))
}

function balanceFrom(data) {
  return data?.broker?.balance?.equity || data?.broker?.balance || {}
}

function positionRows(data) {
  const rows = data?.broker?.positions?.positions ?? data?.broker?.positions
  return Array.isArray(rows) ? rows : []
}

function unwrapPosition(row) {
  const position = row.position || row
  const market = row.market || {}
  return { position, market }
}

function statusClass(status) {
  return `status-${text(status, "unknown").toLowerCase().replaceAll("_", "-")}`
}

function addMessage(role, body) {
  const div = document.createElement("div")
  div.className = `message ${role}`
  div.textContent = body
  els.chatLog.appendChild(div)
  els.chatLog.scrollTop = els.chatLog.scrollHeight
}

function lineItem(title, detail, meta = "", className = "") {
  const div = document.createElement("article")
  div.className = `item ${className}`.trim()
  const strong = document.createElement("strong")
  strong.textContent = title
  const small = document.createElement("small")
  small.textContent = detail
  div.append(strong, small)
  if (meta) {
    const em = document.createElement("em")
    em.textContent = meta
    div.appendChild(em)
  }
  return div
}

function ruleItem(rule) {
  const threshold = rule.threshold === null || rule.threshold === undefined ? "" : ` ${rule.threshold}`
  const last = rule.last_triggered_at ? `last ${rule.last_triggered_at}` : "not triggered"
  const div = lineItem(
    `${rule.epic} ${rule.rule_type} ${rule.condition}${threshold}`,
    `${rule.enabled ? "enabled" : "disabled"} / ${rule.state || "inactive"} / cooldown ${rule.cooldown_seconds}s`,
    last,
    rule.enabled ? "status-approved" : "status-blocked",
  )
  const actions = document.createElement("div")
  actions.className = "item-actions"
  const disable = document.createElement("button")
  disable.type = "button"
  disable.className = "mini-button"
  disable.textContent = "Disable"
  disable.disabled = !rule.enabled
  disable.addEventListener("click", async () => {
    try {
      const res = await fetch(`/api/notifications/rules/${rule.id}/disable`, { method: "POST" })
      await readResponse(res)
      await loadDashboard()
    } catch (error) {
      addMessage("agent", `Alert error: ${error.message}`)
    }
  })
  actions.appendChild(disable)
  div.appendChild(actions)
  return div
}

function renderPosition(row) {
  const { position, market } = unwrapPosition(row)
  const direction = text(position.direction || position.side).toUpperCase()
  const epic = text(position.epic || market.epic || market.instrumentName, "MARKET")
  const upl = Number(position.upl ?? position.profitLoss ?? position.pnl)
  const article = document.createElement("article")
  article.className = `position-row ${direction === "SELL" ? "short" : "long"}`
  article.innerHTML = `
    <div>
      <span>${direction}</span>
      <strong>${epic}</strong>
      <small>${text(position.dealId || position.deal_id || position.id, "no deal id")}</small>
    </div>
    <div>
      <span>Size</span>
      <strong>${compactNumber(position.size)}</strong>
      <small>entry ${compactNumber(position.level ?? position.entryLevel)}</small>
    </div>
    <div>
      <span>Market</span>
      <strong>${text(market.marketStatus || market.status, "unknown")}</strong>
      <small>bid ${compactNumber(market.bid)} / ask ${compactNumber(market.offer ?? market.ask)}</small>
    </div>
    <div class="${upl >= 0 ? "positive" : "negative"}">
      <span>Open P/L</span>
      <strong>${money(upl)}</strong>
      <small>${text(position.currency || market.currencyCode, "")}</small>
    </div>
  `
  return article
}

function renderHealth(components = {}) {
  els.healthGrid.replaceChildren()
  for (const [name, component] of Object.entries(components)) {
    const div = document.createElement("div")
    const status = text(component?.status, "unknown")
    div.className = `health-cell ${statusClass(status)}`
    div.innerHTML = `<span>${name.replaceAll("_", " ")}</span><strong>${status}</strong>`
    els.healthGrid.appendChild(div)
  }
}

function renderDashboard(data) {
  const balance = balanceFrom(data)
  const positions = positionRows(data)
  const health = data.capital?.deep_health || {}
  const components = health.components || {}
  const trading = components.trading || {}
  const reconciliation = components.reconciliation || {}
  const ticketSummary = data.agent.ticket_summary || {}
  const ticketCount = data.agent.tickets.length
  const openExposure = positions.reduce((sum, row) => {
    const { position } = unwrapPosition(row)
    const size = Number(position.size)
    return Number.isFinite(size) ? sum + Math.abs(size) : sum
  }, 0)
  const firstPosition = positions[0] ? unwrapPosition(positions[0]) : null

  els.equity.textContent = money(balance.balance ?? balance.equity)
  els.available.textContent = `available ${money(balance.available)}`
  els.profitLoss.textContent = money(balance.profitLoss ?? balance.pnl)
  els.profitLoss.className = Number(balance.profitLoss ?? balance.pnl) >= 0 ? "positive" : "negative"
  els.deposit.textContent = `deposit ${money(balance.deposit)}`
  els.exposure.textContent = compactNumber(openExposure)
  els.positionCount.textContent = `${positions.length} position${positions.length === 1 ? "" : "s"}`
  els.writes.textContent = data.config.trading_writes_enabled ? "enabled" : "disabled"
  els.tradeMode.textContent = `agent ${data.agent.mode} / capital ${text(trading.mode, "unknown")}`
  els.capitalHealth.textContent = text(health.status || data.broker.health?.status, "unknown")
  els.broker.textContent = data.broker.health_error ? "broker error" : `broker ${text(data.broker.health?.status, "unknown")}`
  els.ticketCount.textContent = String(ticketCount).padStart(2, "0")
  els.ticketBreakdown.textContent = Object.entries(ticketSummary).map(([key, value]) => `${key} ${value}`).join(" / ") || "none"
  els.stackStatus.textContent = health.status || data.broker.health?.status || "local"
  els.marketStatus.textContent = firstPosition ? `MARKET ${text(firstPosition.market.marketStatus || firstPosition.market.status)}` : "MARKET --"
  els.reconciliation.textContent = `RECON ${text(reconciliation.status, "unknown")}`
  els.telegramStatus.textContent = data.config.notifications?.telegram_configured ? "BOT READY" : "BOT CONFIG"
  els.mode.textContent = data.agent.mode
  els.modeSelect.value = data.agent.mode
  els.canvasConnect.hidden = data.canvas.connected || !data.canvas.configured

  els.positions.replaceChildren()
  positions.forEach((position) => els.positions.appendChild(renderPosition(position)))

  els.tickets.replaceChildren()
  for (const ticket of data.agent.tickets) {
    const risk = ticket.risk?.errors?.length ? ticket.risk.errors.join("; ") : ticket.risk?.status || "unknown"
    const deal = ticket.deal_id ? `deal ${ticket.deal_id}` : ticket.order_type
    els.tickets.appendChild(
      lineItem(
        `${ticket.epic} ${ticket.direction} ${compactNumber(ticket.size)}`,
        `${ticket.status} / risk ${risk}`,
        `${ticket.id} / ${deal}`,
        statusClass(ticket.status),
      ),
    )
  }

  els.actions.replaceChildren()
  for (const action of data.agent.actions || []) {
    els.actions.appendChild(
      lineItem(
        action.summary || action.action,
        `${action.action} / ${text(action.status, "no status")}`,
        text(action.created_at, ""),
        statusClass(action.status),
      ),
    )
  }

  els.tradeLogs.replaceChildren()
  const logs = data.capital?.trade_logs?.logs || []
  for (const log of logs) {
    const payload = typeof log.payload === "object" && log.payload !== null ? log.payload : {}
    const detail = payload.reason || payload.status || payload.epic || payload.deal_id || text(log.correlation_id, "capital event")
    els.tradeLogs.appendChild(lineItem(log.event_type, detail, text(log.created_at, ""), statusClass(payload.status)))
  }

  renderHealth(components)

  els.notifications.replaceChildren()
  for (const rule of data.agent.notification_rules || []) {
    els.notifications.appendChild(ruleItem(rule))
  }
  for (const event of data.agent.notification_events || []) {
    els.notifications.appendChild(
      lineItem(
        event.title,
        event.delivered ? "delivered" : `not delivered / ${text(event.error, "pending")}`,
        text(event.created_at, ""),
        event.delivered ? "status-approved" : "status-degraded",
      ),
    )
  }

  els.memories.replaceChildren()
  for (const memory of data.agent.memories || []) {
    els.memories.appendChild(lineItem(memory.title || memory.memory_type, memory.content, memory.scope || memory.memory_type))
  }

  els.browserSnapshots.replaceChildren()
  for (const snapshot of data.browser?.snapshots || []) {
    els.browserSnapshots.appendChild(lineItem(snapshot.title || "Imported page", snapshot.url, snapshot.created_at || snapshot.source))
  }

  document.body.dataset.capitalStatus = text(health.status, "unknown")
}

async function readResponse(res) {
  const body = await res.text()
  let data
  try {
    data = body ? JSON.parse(body) : {}
  } catch {
    throw new Error(`Agent returned HTTP ${res.status}: ${body.slice(0, 240)}`)
  }
  if (!res.ok) throw new Error(data.detail || `Agent returned HTTP ${res.status}`)
  return data
}

async function loadDashboard() {
  const res = await fetch("/api/dashboard")
  renderDashboard(await readResponse(res))
}

els.goldTypeButtons.forEach((button) => {
  button.addEventListener("click", () => setGoldChartType(button.dataset.goldType))
})

els.goldIntervalButtons.forEach((button) => {
  button.addEventListener("click", () => setGoldInterval(button.dataset.goldInterval))
})

els.goldRangeButtons.forEach((button) => {
  button.addEventListener("click", () => setGoldRange(button.dataset.goldRange))
})

els.goldFitButton.addEventListener("click", applyGoldRange)

els.goldFullscreenButton.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement === els.goldPanel) {
      await document.exitFullscreen()
    } else {
      await els.goldPanel.requestFullscreen()
    }
  } catch (error) {
    els.goldChartStatus.title = error.message
  }
})

document.addEventListener("fullscreenchange", syncGoldFullscreen)
syncGoldToolbar()
syncGoldFullscreen()

els.modeSelect.addEventListener("change", async () => {
  const res = await fetch("/api/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: els.modeSelect.value }),
  })
  await readResponse(res)
  await loadDashboard()
})

els.refreshButton.addEventListener("click", () => {
  loadDashboard().catch((error) => addMessage("agent", `Dashboard error: ${error.message}`))
  loadGoldCandles()
})

els.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault()
  const message = els.chatInput.value.trim()
  if (!message) return
  els.chatInput.value = ""
  addMessage("user", message)

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: state.sessionId }),
    })
    const data = await readResponse(res)
    state.sessionId = data.session_id
    addMessage("agent", data.response || JSON.stringify(data))
    await loadDashboard()
  } catch (error) {
    addMessage("agent", `Error: ${error.message}`)
  }
})

function syncAlertForm() {
  const type = els.alertType.value
  const needsCondition = type === "price" || type === "position_pl"
  const needsThreshold = needsCondition
  els.alertCondition.disabled = !needsCondition
  els.alertThreshold.disabled = !needsThreshold
  els.alertEpic.disabled = type === "health"
}

els.alertType.addEventListener("change", syncAlertForm)

els.alertForm.addEventListener("submit", async (event) => {
  event.preventDefault()
  const type = els.alertType.value
  const payload = {
    rule_type: type,
    epic: type === "health" ? "CAPITAL_TRADER" : els.alertEpic.value.trim().toUpperCase(),
    condition: els.alertCondition.value,
    cooldown_seconds: Number(els.alertCooldown.value || 900),
    notify_recovery: els.alertRecovery.checked,
  }
  if (type === "price" || type === "position_pl") {
    payload.threshold = Number(els.alertThreshold.value)
  }
  try {
    const res = await fetch("/api/notifications/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
    await readResponse(res)
    els.alertThreshold.value = ""
    await loadDashboard()
  } catch (error) {
    addMessage("agent", `Alert error: ${error.message}`)
  }
})

els.evaluateAlerts.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/notifications/evaluate", { method: "POST" })
    const data = await readResponse(res)
    addMessage("agent", `Alerts checked: ${data.checked}; triggered: ${data.triggered.length}; errors: ${data.errors.length}`)
    await loadDashboard()
  } catch (error) {
    addMessage("agent", `Alert error: ${error.message}`)
  }
})

els.presetAlerts.addEventListener("click", async () => {
  const epic = els.alertEpic.value.trim().toUpperCase() || "GOLD"
  try {
    const res = await fetch("/api/notifications/presets/position", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        epic,
        delta: 50,
        cooldown_seconds: Number(els.alertCooldown.value || 900),
        notify_recovery: els.alertRecovery.checked,
      }),
    })
    const data = await readResponse(res)
    addMessage("agent", `Created ${data.rules.length} ${data.epic} alert presets around P/L ${money(data.current_upl)}.`)
    await loadDashboard()
  } catch (error) {
    addMessage("agent", `Alert preset error: ${error.message}`)
  }
})

function updateClock() {
  els.systemTime.textContent = new Date().toLocaleTimeString([], { hour12: false })
}

updateClock()
syncAlertForm()
setInterval(updateClock, 1000)
if (initGoldChart()) {
  loadGoldCandles()
  setInterval(loadGoldCandles, GOLD_REFRESH_MS)
}
loadDashboard().catch((error) => {
  els.stackStatus.textContent = "dashboard error"
  addMessage("agent", `Dashboard error: ${error.message}`)
})
