const API_BASE = '/api';
const EPICS = ['GOLD', 'US500', 'BTCUSD'];
const RESOLUTIONS = {
    '1m':  { api: 'MINUTE',    label: '1m',  minutes: 1 },
    '5m':  { api: 'MINUTE_5',  label: '5m',  minutes: 5 },
    '15m': { api: 'MINUTE_15', label: '15m', minutes: 15 },
    '1h':  { api: 'HOUR',      label: '1h',  minutes: 60 },
    '4h':  { api: 'HOUR_4',    label: '4h',  minutes: 240 },
    '1D':  { api: 'DAY',       label: '1D',  minutes: 1440 },
};
const SSE_URL = API_BASE + '/v1/sse/stream/prices';
const GOLD_CSV_URL = API_BASE + '/v1/market/gold/candles.csv';
const HISTORY_REFRESH_MS = 60000;
const query = new URLSearchParams(window.location.search);
const requestedEpic = query.get('epic');
const requestedResolution = query.get('resolution');

let selectedEpic = EPICS.includes(requestedEpic) ? requestedEpic : 'GOLD';
let selectedRes = Object.prototype.hasOwnProperty.call(RESOLUTIONS, requestedResolution) ? requestedResolution : '1m';
let historyStart = '';
let historyEnd = '';
let historyLimit = Math.min(10000, Math.max(1, Number(query.get('limit')) || 1000));
let chart;
let candleSeries;
let volumeSeries;
let candleBuilder = null;
let sse = null;
let sseReconnectTimer = null;
let historyRefreshTimer = null;
let initialFitDone = false;
let startToken = 0;

const $ = selector => document.querySelector(selector);
const $$ = selector => document.querySelectorAll(selector);

const THEME = {
    layout: {
        background: { color: '#0b0f17' },
        textColor: '#8b95a8',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
    },
    grid: {
        vertLines: { color: 'rgba(255,255,255,0.04)' },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
    },
    crosshair: {
        mode: 0,
        vertLine: { color: 'rgba(255,255,255,0.15)', style: 2, width: 1, labelBackgroundColor: '#1e2a3a' },
        horzLine: { color: 'rgba(255,255,255,0.15)', style: 2, width: 1, labelBackgroundColor: '#1e2a3a' },
    },
    timeScale: {
        borderColor: 'rgba(45, 53, 72, 0.6)',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: timestamp => {
            const date = new Date(timestamp * 1000);
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            return hours + ':' + minutes;
        },
    },
    rightPriceScale: { borderColor: 'rgba(45, 53, 72, 0.6)' },
};

const CANDLE_STYLE = {
    upColor: '#2ecc9a',
    downColor: '#e85555',
    borderUpColor: '#2ecc9a',
    borderDownColor: '#e85555',
    wickUpColor: '#2ecc9a',
    wickDownColor: '#e85555',
};

const VOLUME_STYLE = {
    color: 'rgba(91, 141, 239, 0.3)',
    priceFormat: { type: 'volume' },
    priceScaleId: 'volume',
};

class CandleBuilder {
    constructor(resolutionMinutes, onNewCandle) {
        this.resolutionMs = resolutionMinutes * 60 * 1000;
        this.closed = [];
        this.open = null;
        this.onNewCandle = onNewCandle || (() => {});
    }

    seed(candles) {
        this.closed = candles.slice(0, -1).map(candle => ({ ...candle }));
        this.open = candles.length ? { ...candles[candles.length - 1] } : null;
    }

    addTick(price) {
        const now = Date.now();
        const bucket = Math.floor(now / this.resolutionMs) * this.resolutionMs;
        const time = Math.floor(bucket / 1000);
        if (this.open && this.open.time === time) {
            this.open.high = Math.max(this.open.high, price);
            this.open.low = Math.min(this.open.low, price);
            this.open.close = price;
            return;
        }
        if (this.open) {
            this.closed.push(this.open);
            this.onNewCandle();
        }
        this.open = { time, open: price, high: price, low: price, close: price, volume: 0 };
    }

    getAll() {
        return this.open ? [...this.closed, { ...this.open }] : [...this.closed];
    }
}

function midpoint(bid, ask) {
    const bidValue = Number(bid);
    const askValue = Number(ask);
    if (!Number.isFinite(bidValue) || !Number.isFinite(askValue)) return null;
    return (bidValue + askValue) / 2;
}

function normalizeCandles(candles) {
    const byTime = new Map();
    candles.forEach(candle => {
        if (Number.isFinite(candle.time)) byTime.set(candle.time, candle);
    });
    return [...byTime.values()].sort((left, right) => left.time - right.time);
}

function parseCsv(text) {
    const lines = text.trim().split(/\r?\n/).filter(Boolean);
    if (lines.length < 2) return [];
    const headers = lines.shift().split(',');
    return lines.map(line => {
        const values = line.split(',');
        return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? '']));
    });
}

function storedCandle(row) {
    const candle = {
        time: Number(row.timestamp),
        open: midpoint(row.open_bid, row.open_ask),
        high: midpoint(row.high_bid, row.high_ask),
        low: midpoint(row.low_bid, row.low_ask),
        close: midpoint(row.close_bid, row.close_ask),
        volume: Number(row.volume) || 0,
    };
    return Object.values(candle).every(value => typeof value === 'number' && Number.isFinite(value)) ? candle : null;
}

function brokerCandle(item) {
    const timestamp = Date.parse(item.snapshotTimeUTC || item.snapshotTime) / 1000;
    const candle = {
        time: timestamp,
        open: midpoint(item.openPrice?.bid, item.openPrice?.ask),
        high: midpoint(item.highPrice?.bid, item.highPrice?.ask),
        low: midpoint(item.lowPrice?.bid, item.lowPrice?.ask),
        close: midpoint(item.closePrice?.bid, item.closePrice?.ask),
        volume: Number(item.lastTradedVolume ?? item.volume) || 0,
    };
    return Object.values(candle).every(value => typeof value === 'number' && Number.isFinite(value)) ? candle : null;
}

function goldCsvUrl() {
    const params = new URLSearchParams({ limit: String(historyLimit) });
    if (historyStart) params.set('start', historyStart);
    if (historyEnd) params.set('end', historyEnd);
    return GOLD_CSV_URL + '?' + params.toString();
}

async function loadHistoricalCandles() {
    if (selectedEpic === 'GOLD' && selectedRes === '1m') {
        const response = await fetch(goldCsvUrl());
        if (!response.ok) throw new Error('Stored Gold candles are unavailable');
        return normalizeCandles(parseCsv(await response.text()).map(storedCandle).filter(Boolean));
    }
    const params = new URLSearchParams({
        resolution: RESOLUTIONS[selectedRes].api,
        max_points: String(historyLimit),
    });
    const response = await fetch(`${API_BASE}/v1/market/prices/${selectedEpic}?${params}`);
    if (!response.ok) throw new Error('Broker candles are unavailable');
    const payload = await response.json();
    return normalizeCandles((payload.prices || []).map(brokerCandle).filter(Boolean));
}

function connectSSE() {
    if (sse) {
        sse.close();
        sse = null;
    }
    clearTimeout(sseReconnectTimer);
    sse = new EventSource(SSE_URL);
    sse.onmessage = event => {
        try {
            const data = JSON.parse(event.data);
            if (data.epic !== selectedEpic || !candleBuilder) return;
            const price = midpoint(data.bid, data.ask);
            if (price === null) return;
            candleBuilder.addTick(price);
            renderChart();
        } catch (_) {
            return;
        }
    };
    sse.onerror = () => {
        sse.close();
        sse = null;
        sseReconnectTimer = setTimeout(connectSSE, 5000);
    };
}

function renderChart() {
    const candles = candleBuilder ? candleBuilder.getAll() : [];
    if (candles.length === 0) {
        $('#chart-status').textContent = 'Waiting for live ticks...';
        return;
    }
    candleSeries.setData(candles);
    volumeSeries.setData(candles.map(candle => ({
        time: candle.time,
        value: candle.volume || 0,
        color: candle.close >= candle.open ? 'rgba(46,204,154,0.3)' : 'rgba(232,85,85,0.3)',
    })));
    if (!initialFitDone) {
        chart.timeScale().fitContent();
        initialFitDone = true;
    }
    const last = candles[candles.length - 1];
    const change = last.close - last.open;
    const percent = last.open !== 0 ? change / last.open * 100 : 0;
    const decimals = last.close > 100 ? 2 : last.close > 1 ? 4 : 6;
    $('#price-current').textContent = last.close.toFixed(decimals);
    const changeElement = $('#price-change');
    changeElement.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(decimals)} (${percent >= 0 ? '+' : ''}${percent.toFixed(2)}%)`;
    changeElement.className = 'price-change ' + (change >= 0 ? 'up' : 'down');
    const resolution = RESOLUTIONS[selectedRes];
    const source = selectedEpic === 'GOLD' && selectedRes === '1m' ? 'stored + live' : 'broker + live';
    $('#chart-title').textContent = `${selectedEpic} · ${resolution.label}`;
    $('#chart-status').textContent = `${candles.length} candles · ${source}`;
}

async function refreshHistoricalCandles(token) {
    try {
        const candles = await loadHistoricalCandles();
        if (token !== startToken || !candleBuilder) return;
        candleBuilder.seed(candles);
        renderChart();
    } catch (error) {
        if (token !== startToken) return;
        $('#chart-status').textContent = 'Live only · ' + error.message;
    }
}

async function startMonitor() {
    startToken += 1;
    const token = startToken;
    clearInterval(historyRefreshTimer);
    candleBuilder = new CandleBuilder(RESOLUTIONS[selectedRes].minutes, () => {
        if (initialFitDone) chart.timeScale().scrollToRealTime();
    });
    candleSeries.setData([]);
    volumeSeries.setData([]);
    initialFitDone = false;
    $('#chart-status').textContent = 'Loading candle history...';
    updateHistoryControls();
    await refreshHistoricalCandles(token);
    if (token !== startToken) return;
    historyRefreshTimer = setInterval(() => refreshHistoricalCandles(token), HISTORY_REFRESH_MS);
    if (!sse) connectSSE();
}

function initChart() {
    const container = $('#chart-container');
    const rect = container.getBoundingClientRect();
    chart = LightweightCharts.createChart(container, {
        ...THEME,
        width: rect.width,
        height: Math.max(400, Math.min(window.innerHeight - 280, 600)),
    });
    candleSeries = chart.addCandlestickSeries(CANDLE_STYLE);
    volumeSeries = chart.addHistogramSeries(VOLUME_STYLE);
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    const observer = new ResizeObserver(() => {
        const current = container.getBoundingClientRect();
        chart.applyOptions({ width: current.width, height: Math.max(400, Math.min(window.innerHeight - 280, 600)) });
    });
    observer.observe(container);
}

function readHistoryControls() {
    const startValue = $('#history-start').value;
    const endValue = $('#history-end').value;
    historyStart = startValue ? new Date(startValue).toISOString() : '';
    historyEnd = endValue ? new Date(endValue).toISOString() : '';
    historyLimit = Math.min(10000, Math.max(1, Number($('#history-limit').value) || 1000));
    $('#history-limit').value = String(historyLimit);
}

function updateHistoryControls() {
    const storedGold = selectedEpic === 'GOLD' && selectedRes === '1m';
    $('#history-controls').hidden = !storedGold;
    if (storedGold) $('#download-candles').href = goldCsvUrl();
}

function initControls() {
    const epicBar = $('#epic-bar');
    const resolutionBar = $('#res-bar');
    EPICS.forEach(epic => {
        const button = document.createElement('button');
        button.className = 'control-btn' + (epic === selectedEpic ? ' active' : '');
        button.textContent = epic === 'BTCUSD' ? 'BTC' : epic;
        button.dataset.epic = epic;
        button.addEventListener('click', () => {
            selectedEpic = epic;
            $$('#epic-bar .control-btn').forEach(item => item.classList.remove('active'));
            button.classList.add('active');
            startMonitor();
        });
        epicBar.appendChild(button);
    });
    Object.keys(RESOLUTIONS).forEach(resolution => {
        const button = document.createElement('button');
        button.className = 'control-btn' + (resolution === selectedRes ? ' active' : '');
        button.textContent = resolution;
        button.dataset.res = resolution;
        button.addEventListener('click', () => {
            selectedRes = resolution;
            $$('#res-bar .control-btn').forEach(item => item.classList.remove('active'));
            button.classList.add('active');
            startMonitor();
        });
        resolutionBar.appendChild(button);
    });
    $('#history-limit').value = String(historyLimit);
    $('#apply-history').addEventListener('click', () => {
        readHistoryControls();
        startMonitor();
    });
    $('#clear-history').addEventListener('click', () => {
        $('#history-start').value = '';
        $('#history-end').value = '';
        readHistoryControls();
        startMonitor();
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initChart();
    initControls();
    startMonitor();
});

window.addEventListener('beforeunload', () => {
    if (sse) sse.close();
    clearInterval(historyRefreshTimer);
});
