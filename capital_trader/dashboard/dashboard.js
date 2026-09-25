const API_BASE = '/api';
const REFRESH_POSITIONS_MS = 30000;
const REFRESH_EQUITY_MS = 60000;
const REFRESH_ACTIVITY_MS = 60000;
const REFRESH_TICKERS_MS = 60000;
const REFRESH_ORDERS_MS = 30000;
const REFRESH_STATS_MS = 60000;

const TICKER_EPICS = ['GOLD', 'US500', 'BTCUSD'];
const prevPrices = {};
const lastSnapshots = {};
let sseConnected = false;

const fmt = {
    currency: (v) => {
        if (v == null) return '—';
        const n = Number(v);
        if (isNaN(n)) return '—';
        return new Intl.NumberFormat('en-US', {
            style: 'currency', currency: 'NOK',
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        }).format(n);
    },
    number: (v, d = 2) => {
        if (v == null) return '—';
        const n = Number(v);
        if (isNaN(n)) return '—';
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: d, maximumFractionDigits: d,
        }).format(n);
    },
    date: (iso) => {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
        } catch { return '—'; }
    },
    shortDate: (iso) => {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
        } catch { return '—'; }
    },
};

const $ = (sel) => document.querySelector(sel);

function now() {
    return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

function updateClock() {
    const el = $('#last-refresh');
    if (el) el.textContent = now();
}

function sectionTime(id) {
    const el = $(`#${id}`);
    if (el) el.textContent = now();
}

function applyNumericClass(el, value) {
    if (!el) return;
    if (value == null) { el.className = 'metric-value muted'; return; }
    const n = Number(value);
    if (isNaN(n)) { el.className = 'metric-value muted'; return; }
    el.className = n >= 0 ? 'metric-value positive' : 'metric-value negative';
}

async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) {
        const body = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}${body ? ': ' + body.slice(0, 120) : ''}`);
    }
    return resp.json();
}

function formatAction(type, status, source) {
    const t = (type || '').toUpperCase();
    const s = (status || '').toUpperCase();
    const src = (source || '').toUpperCase();
    if (t === 'WORKING_ORDER') {
        if (s === 'CREATED') return 'ORDER OPENED';
        if (s === 'EXECUTED') return 'ORDER FILLED';
        if (s === 'CANCELLED') return 'ORDER CANCEL';
        if (s === 'MODIFIED') return 'ORDER MODIFIED';
        if (s === 'ACCEPTED') return 'ORDER ACCEPT';
        return 'ORDER ' + s;
    }
    if (t === 'POSITION') {
        if (src === 'SL') return 'STOP LOSS';
        return 'POSITION';
    }
    if (t === 'EDIT_STOP_AND_LIMIT') return 'EDIT STOP';
    return t.replace(/_/g, ' ');
}

function actionClass(type, status, source) {
    const t = (type || '').toUpperCase();
    const s = (status || '').toUpperCase();
    const src = (source || '').toUpperCase();
    if (t === 'WORKING_ORDER' && (s === 'CANCELLED' || s === 'EXECUTED')) return 'close';
    if (t === 'POSITION' && src === 'SL') return 'close';
    if (s === 'CREATED' || (t === 'POSITION' && src !== 'SL')) return 'open';
    if (s === 'MODIFIED' || t === 'EDIT_STOP_AND_LIMIT') return 'amend';
    if (s === 'EXECUTED') return 'filled';
    return '';
}

let hasPortfolio = false;
let hasPositions = false;
let hasActivity = false;
let hasOrders = false;
let hasStats = false;
let hasAlerts = false;

function staleIndicator(on) {
    const el = $('#stale-warning');
    if (!el) return;
    el.textContent = on ? '⚠ stale' : '';
    el.style.display = on ? 'inline' : 'none';
}

async function loadSettings() {
    try {
        const data = await fetchJSON(`${API_BASE}/debug/settings`);
        const env = (data.environment || 'demo').toLowerCase();
        const badge = $('#env-badge');
        if (badge) {
            badge.textContent = env === 'live' ? 'LIVE' : 'DEMO';
            if (env === 'live') badge.classList.add('live');
        }
        const st = $('#status-text');
        if (st) st.textContent = 'Connected';
        const dot = $('.status-dot');
        if (dot) dot.classList.remove('error');
    } catch (e) {
        console.warn('Settings unavailable:', e.message);
    }
}

async function loadPortfolio() {
    const balEl = $('#balance-value');
    const eqEl = $('#equity-value');
    const pnlEl = $('#pnl-value');
    const pnlSub = $('#pnl-sub');
    const marVal = $('#margin-value');
    const marBar = $('#margin-bar');
    try {
        const data = await fetchJSON(`${API_BASE}/v1/accounts`);
        const accts = data.accounts || [];
        if (accts.length > 0) {
            const acct = accts[0];
            const bals = acct.balance || {};
            const bal = bals.balance;
            const avail = bals.available;
            const pnl = bals.profitLoss;
            const deposit = bals.deposit;
            const curr = acct.currency || 'NOK';

            if (balEl) balEl.textContent = bal != null ? fmt.currency(bal) : '—';
            if (eqEl) eqEl.textContent = avail != null ? fmt.currency(avail) : '—';

            if (pnlEl) {
                if (pnl != null) {
                    pnlEl.textContent = fmt.currency(pnl);
                    applyNumericClass(pnlEl, pnl);
                } else {
                    pnlEl.textContent = '—';
                    pnlEl.className = 'metric-value muted';
                }
            }

            if (pnlSub) {
                pnlSub.textContent = curr;
            }

            if (marVal && bal != null && avail != null) {
                const used = bal - avail;
                marVal.textContent = fmt.currency(used);
                if (bal > 0) {
                    const pct = Math.min((used / bal) * 100, 100);
                    if (marBar) marBar.style.width = pct + '%';
                }
            } else if (marVal) {
                const d = deposit != null ? deposit : 0;
                const used = d - (avail || 0);
                marVal.textContent = used > 0 ? fmt.currency(used) : '—';
            }

            hasPortfolio = true;
        } else if (!hasPortfolio) {
            if (balEl) balEl.textContent = '—';
            if (eqEl) eqEl.textContent = '—';
            if (pnlEl) { pnlEl.textContent = '—'; pnlEl.className = 'metric-value muted'; }
            if (marVal) marVal.textContent = '—';
        }
    } catch (e) {
        console.warn('Portfolio unavailable:', e.message);
        if (!hasPortfolio) {
            if (balEl) balEl.textContent = '—';
            if (eqEl) eqEl.textContent = '—';
            if (pnlEl) { pnlEl.textContent = '—'; pnlEl.className = 'metric-value muted'; }
            if (marVal) marVal.textContent = '—';
        }
    }
    updateClock();
}

function renderExposure(positions) {
    const card = $('#exposure-card');
    if (!card) return;
    if (!positions || positions.length === 0) {
        card.style.display = 'none';
        return;
    }
    let long = 0, short = 0;
    positions.forEach((item) => {
        const p = item.position || {};
        const size = Number(p.size) || 0;
        if ((p.direction || '').toUpperCase() === 'BUY') long += size;
        else short += size;
    });
    const total = long + short;
    if (total === 0) { card.style.display = 'none'; return; }

    card.style.display = 'block';
    $('#expo-long').textContent = fmt.number(long, 2);
    $('#expo-short').textContent = fmt.number(short, 2);
    const net = long - short;
    const netEl = $('#expo-net');
    netEl.textContent = (net >= 0 ? 'Long ' : 'Short ') + fmt.number(Math.abs(net), 2);
    netEl.style.color = net >= 0 ? 'var(--green)' : 'var(--red)';

    const longPct = (long / total) * 100;
    const shortPct = (short / total) * 100;
    $('#expo-bar-long').style.width = longPct + '%';
    $('#expo-bar-short').style.width = shortPct + '%';
}

async function loadPositions() {
    const tbody = $('#positions-body');
    if (!tbody) return;
    const badge = $('#positions-badge');
    try {
        const data = await fetchJSON(`${API_BASE}/v1/positions`);
        const positions = data.positions || [];
        if (badge) badge.textContent = positions.length;

        renderExposure(positions);

        if (positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">No open positions</td></tr>';
        } else {
            tbody.innerHTML = positions.map((item) => {
                const p = item.position || {};
                const m = item.market || {};
                const dealId = p.dealId ?? '';
                const epic = m.epic ?? '';
                const dir = (p.direction || '').toUpperCase();
                const size = p.size;
                const level = p.level ?? p.openLevel;
                const stopLevel = p.stopLevel;
                const upl = p.upl;
                const status = (p.status || 'OPEN').toUpperCase();
                const dirClass = dir === 'BUY' ? 'dir-buy' : 'dir-sell';
                const pnlClass = upl != null ? (Number(upl) >= 0 ? 'positive' : 'negative') : '';

                return `<tr>
                    <td class="mono">${dealId}</td>
                    <td><strong>${epic}</strong></td>
                    <td class="${dirClass}">${dir}</td>
                    <td class="mono">${fmt.number(size, 2)}</td>
                    <td class="mono">${fmt.number(level)}</td>
                    <td class="mono">${stopLevel != null ? fmt.number(stopLevel) : '—'}</td>
                    <td class="mono ${pnlClass}">${upl != null ? fmt.currency(upl) : '—'}</td>
                    <td><span class="status-badge ${status === 'OPEN' ? 'open' : ''}">${status}</span></td>
                </tr>`;
            }).join('');
        }
        hasPositions = true;
        staleIndicator(false);
        sectionTime('positions-ts');
    } catch (e) {
        console.warn('Positions unavailable:', e.message);
        if (!hasPositions) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">Cannot reach broker API</td></tr>';
            if (badge) badge.textContent = '—';
        } else {
            staleIndicator(true);
        }
    }
}

async function loadOrders() {
    const tbody = $('#orders-body');
    if (!tbody) return;
    const badge = $('#orders-badge');
    try {
        const data = await fetchJSON(`${API_BASE}/v1/orders`);
        const orders = data.orders || [];
        if (badge) badge.textContent = orders.length;

        if (orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">No working orders</td></tr>';
        } else {
            tbody.innerHTML = orders.map((item) => {
                const o = item.order || item;
                const epic = o.epic || o.marketName || '';
                const dir = (o.direction || '').toUpperCase();
                const size = o.size || o.quantity;
                const limit = o.limitLevel || o.limitLevelDistance;
                const stop = o.stopLevel || o.stopLevelDistance;
                const dirClass = dir === 'BUY' ? 'dir-buy' : 'dir-sell';

                return `<tr>
                    <td><strong>${epic}</strong></td>
                    <td class="${dirClass}">${dir}</td>
                    <td class="mono">${fmt.number(size, 2)}</td>
                    <td class="mono">${limit != null ? fmt.number(limit) : '—'}</td>
                    <td class="mono">${stop != null ? fmt.number(stop) : '—'}</td>
                </tr>`;
            }).join('');
        }
        hasOrders = true;
        sectionTime('orders-ts');
    } catch (e) {
        console.warn('Orders unavailable:', e.message);
        if (!hasOrders) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">Orders unavailable</td></tr>';
            if (badge) badge.textContent = '—';
        }
    }
}

function flashPrice(epic, type, direction) {
    const el = $(`#monitor-${epic} .monitor-price-box.${type}`);
    if (!el) return;
    el.classList.remove('flash-up', 'flash-down');
    void el.offsetWidth;
    el.classList.add('flash-' + direction);
}

function renderMonitor(epic, data) {
    const inst = data.instrument || {};
    const snap = data.snapshot || {};
    const bid = snap.bid;
    const offer = snap.offer;
    const chg = snap.percentageChange;
    const status = snap.marketStatus;
    const updated = snap.updateTime;
    const name = inst.name || epic;

    const prev = prevPrices[epic];
    if (prev) {
        if (bid != null && prev.bid != null && bid !== prev.bid) {
            flashPrice(epic, 'bid', bid > prev.bid ? 'up' : 'down');
        }
        if (offer != null && prev.offer != null && offer !== prev.offer) {
            flashPrice(epic, 'ask', offer > prev.offer ? 'up' : 'down');
        }
    }
    prevPrices[epic] = { bid, offer };

    function txt(id, v) { const el = $(`#${id}`); if (el) el.textContent = v != null ? v : '—'; }

    txt(`monitor-${epic}-name`, name);
    txt(`monitor-${epic}-bid`, bid != null ? fmt.number(bid) : '—');
    txt(`monitor-${epic}-offer`, offer != null ? fmt.number(offer) : '—');

    const statusEl = $(`#monitor-${epic}-status`);
    if (statusEl) {
        const isOpen = (status || '').toUpperCase() === 'OPEN';
        statusEl.textContent = status || '—';
        statusEl.className = 'monitor-status ' + (isOpen ? 'open' : 'closed');
    }

    const spreadEl = $(`#monitor-${epic}-spread`);
    if (spreadEl && bid != null && offer != null) {
        const spread = Math.abs(offer - bid);
        spreadEl.textContent = 'Spread: ' + fmt.number(spread);
    }

    const chgEl = $(`#monitor-${epic}-chg`);
    if (chgEl && chg != null) {
        const nchg = Number(chg);
        chgEl.textContent = (nchg >= 0 ? '+' : '') + nchg.toFixed(2) + '%';
        chgEl.className = 'monitor-chg ' + (nchg >= 0 ? 'up' : 'down');
    } else if (chgEl) {
        chgEl.textContent = '';
        chgEl.className = 'monitor-chg';
    }

    const tsEl = $(`#monitor-${epic}-ts`);
    if (tsEl && updated) {
        try {
            const d = new Date(updated);
            tsEl.textContent = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
        } catch { tsEl.textContent = ''; }
    }
}

function drawSparkline(epic, prices) {
    const svg = document.querySelector(`#spark-${epic} .spark-svg`);
    if (!svg || prices.length < 2) return;

    const vals = prices.map(p => {
        const c = p.closePrice || {};
        return ((Number(c.bid) || 0) + (Number(c.ask) || 0)) / 2;
    });

    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = max - min || 1;
    const w = 100, h = 30;
    const step = w / (vals.length - 1);

    const points = vals.map((v, i) => {
        const x = i * step;
        const y = h - ((v - min) / range) * (h - 2) - 1;
        return `${x},${y}`;
    });

    const up = vals[vals.length - 1] >= vals[0];
    const color = up ? 'var(--green)' : 'var(--red)';

    const fillGrad = up ? `url(#gradUp-${epic})` : `url(#gradDown-${epic})`;
    const d = `M${points.join(' L')}`;
    const fillD = `${d} L${w},${h} L0,${h} Z`;

    svg.innerHTML = `
        <defs>
            <linearGradient id="gradUp-${epic}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="var(--green)" stop-opacity="0.2"/>
                <stop offset="100%" stop-color="var(--green)" stop-opacity="0.02"/>
            </linearGradient>
            <linearGradient id="gradDown-${epic}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="var(--red)" stop-opacity="0.2"/>
                <stop offset="100%" stop-color="var(--red)" stop-opacity="0.02"/>
            </linearGradient>
        </defs>
        <path d="${fillD}" fill="${fillGrad}"/>
        <path d="${d}" stroke="${color}" stroke-linecap="round" stroke-linejoin="round"/>
    `;
}

async function loadSparklines() {
    for (const epic of TICKER_EPICS) {
        try {
            const data = await fetchJSON(`${API_BASE}/v1/market/prices/${epic}?resolution=MINUTE&max=60`);
            const prices = data.prices || [];
            drawSparkline(epic, prices);
        } catch (e) {
            console.warn(`Sparkline ${epic} unavailable:`, e.message);
        }
    }
}

function connectPriceStream() {
    const es = new EventSource(`${API_BASE}/v1/sse/stream/prices`);
    es.onopen = () => {
        sseConnected = true;
        const el = $('#ticker-status');
        if (el) el.textContent = 'Live';
    };
    es.onmessage = (e) => {
        try {
            const tick = JSON.parse(e.data);
            const epic = tick.epic;
            const snap = lastSnapshots[epic];
            if (!snap) return;

            snap.snapshot.bid = tick.bid;
            snap.snapshot.offer = tick.ask;
            renderMonitor(epic, snap);

            const bidEl = $(`#ticker-${epic}-bid`);
            const offerEl = $(`#ticker-${epic}-offer`);
            if (bidEl && tick.bid != null) {
                bidEl.textContent = fmt.number(tick.bid);
                const prev = prevPrices[epic];
                if (prev && prev.bid != null && tick.bid !== prev.bid) {
                    bidEl.classList.remove('ticker-flash-up', 'ticker-flash-down');
                    void bidEl.offsetWidth;
                    bidEl.classList.add('ticker-flash-' + (tick.bid > prev.bid ? 'up' : 'down'));
                }
            }
            if (offerEl && tick.ask != null) {
                offerEl.textContent = fmt.number(tick.ask);
                const prev = prevPrices[epic];
                if (prev && prev.offer != null && tick.ask !== prev.offer) {
                    offerEl.classList.remove('ticker-flash-up', 'ticker-flash-down');
                    void offerEl.offsetWidth;
                    offerEl.classList.add('ticker-flash-' + (tick.ask > prev.offer ? 'up' : 'down'));
                }
            }
        } catch (err) {
            console.warn('SSE parse error:', err);
        }
    };
    es.onerror = () => {
        sseConnected = false;
        const el = $('#ticker-status');
        if (el) el.textContent = 'Prices delayed';
    };
}

async function loadTickers() {
    const statusEl = $('#ticker-status');
    let anyOk = false;
    for (const epic of TICKER_EPICS) {
        try {
            const data = await fetchJSON(`${API_BASE}/v1/market/${epic}`);
            const snap = data.snapshot || {};
            const bid = snap.bid;
            const offer = snap.offer;
            const chg = snap.percentageChange;

            const bidEl = $(`#ticker-${epic}-bid`);
            const offerEl = $(`#ticker-${epic}-offer`);
            const chgEl = $(`#ticker-${epic}-chg`);

            const prevT = prevPrices[epic];
            if (bidEl && bid != null) {
                bidEl.textContent = fmt.number(bid);
                if (prevT && prevT.bid != null && bid !== prevT.bid) {
                    bidEl.classList.remove('ticker-flash-up', 'ticker-flash-down');
                    void bidEl.offsetWidth;
                    bidEl.classList.add('ticker-flash-' + (bid > prevT.bid ? 'up' : 'down'));
                }
            } else if (bidEl) {
                bidEl.textContent = '—';
            }
            if (offerEl && offer != null) {
                offerEl.textContent = fmt.number(offer);
                if (prevT && prevT.offer != null && offer !== prevT.offer) {
                    offerEl.classList.remove('ticker-flash-up', 'ticker-flash-down');
                    void offerEl.offsetWidth;
                    offerEl.classList.add('ticker-flash-' + (offer > prevT.offer ? 'up' : 'down'));
                }
            } else if (offerEl) {
                offerEl.textContent = '—';
            }

            if (chgEl && chg != null) {
                const nchg = Number(chg);
                chgEl.textContent = (nchg >= 0 ? '+' : '') + nchg.toFixed(2) + '%';
                chgEl.className = 'ticker-chg' + (nchg >= 0 ? ' up' : ' down');
            } else if (chgEl) {
                chgEl.textContent = '';
                chgEl.className = 'ticker-chg';
            }

            lastSnapshots[epic] = JSON.parse(JSON.stringify(data));
            renderMonitor(epic, data);
            anyOk = true;
        } catch (e) {
            console.warn(`Ticker ${epic} unavailable:`, e.message);
        }
    }
    if (statusEl) {
        if (!sseConnected) {
            statusEl.textContent = anyOk ? 'Prices delayed' : 'Prices unavailable';
        }
    }
}

async function loadActivity() {
    const tbody = $('#activity-body');
    if (!tbody) return;
    const badge = $('#activity-badge');
    try {

        const data = await fetchJSON(`${API_BASE}/dashboard/activity`);
        const activities = data.transactions || [];
        if (badge) badge.textContent = activities.length;

        if (activities.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">No recent activity</td></tr>';
        } else {
            // show most recent 50 items, as some may be large (e.g. SL/TP edits with many positions)
/*
dashboard/activity 

  "transactions": [
    {
      "date": "2026-05-08T23:00:15.018",
      "dateUtc": "2026-05-08T21:00:15.018",
      "instrumentName": "GOLD",
      "transactionType": "SWAP",
      "note": "Overnight fee",
      "reference": "127223731574061",
      "size": "3.1",
      "currency": "NOK",
      "status": "PROCESSED"
    },
    {
      "date": "2026-05-08T17:48:02.172",
      "dateUtc": "2026-05-08T15:48:02.172",
      "instrumentName": "GOLD",
      "transactionType": "TRADE",
      "note": "Trade closed",
      "reference": "127204088596174",
      "size": "-16.05",
      "currency": "NOK",
      "status": "PROCESSED",
      "dealId": "00601567-0001-54c4-0000-0000900ac8cb"
    },
    {
      "date": "2026-05-08T17:08:19.545",
      "dateUtc": "2026-05-08T15:08:19.545",
      "instrumentName": "GOLD",
      "transactionType": "TRADE",
      "note": "Trade closed",
      "reference": "127201589804741",
      "size": "-1.2",
      "currency": "NOK",
      "status": "PROCESSED",
      "dealId": "00601567-0001-54c4-0000-0000900a544b"
    },
    {
      "date": "2026-05-08T16:41:31.835",
      "dateUtc": "2026-05-08T14:41:31.835",
      "transactionType": "DEPOSIT",
      "note": "Deposit",
      "reference": "127199903676394",
      "size": "343.0",
      "currency": "NOK",
      "status": "PROCESSED"
    },
    {
      "date": "2026-05-08T16:30:50.312",
      "dateUtc": "2026-05-08T14:30:50.312",
      "instrumentName": "GOLD",
      "transactionType": "TRADE",
      "note": "Trade closed",
      "reference": "127199231529176",
      "size": "-61.83",
      "currency": "NOK",
      "status": "PROCESSED",
      "dealId": "00601567-0001-54c4-0000-00009009fb89"
    },
    {
      "date": "2026-05-08T16:10:32.197",
      "dateUtc": "2026-05-08T14:10:32.197",
      "instrumentName": "GOLD",
      "transactionType": "TRADE",
      "note": "Trade closed",
      "reference": "127197954341002",
      "size": "-66.36",
      "currency": "NOK",
      "status": "PROCESSED",
      "dealId": "00601567-0001-54c4-0000-00009009cead"
    },
    {
      "date": "2026-05-08T14:56:01.527",
      "dateUtc": "2026-05-08T12:56:01.527",
      "instrumentName": "GOLD",
      "transactionType": "TRADE",
      "note": "Trade closed",
      "reference": "127193266193283",
      "size": "1.53",
      "currency": "NOK",
      "status": "PROCESSED",
      "dealId": "00601567-0001-54c4-0000-00009008e2e0"
    },

*/          tbody.innerHTML = activities.slice(0, 50).map((a) => {
                const type = formatAction(a.transactionType, a.status, a.source);
                const cls = actionClass(a.transactionType, a.status, a.source);
                const note = a.note || '';
                const ref = a.reference || '';
                const size = a.size != null ? fmt.currency(a.size) : '—';
                return `<tr>
                    <td class="mono">${fmt.shortDate(a.date)}</td>
                    <td>${a.instrumentName || '—'}</td>
                    <td><span class="action-tag ${cls}">${type}</span></td>
                    <td>${note}${size !== '—' ? ' <span class="mono ' + (Number(a.size) >= 0 ? 'positive' : 'negative') + '">' + size + '</span>' : ''} <span class="ref">(${ref})</span></td>
                </tr>`;
            }).join('');
        }
        hasActivity = true;
        sectionTime('activity-ts');
    } catch (e) {
        console.warn('Activity unavailable:', e.message);
        if (!hasActivity) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">Activity feed unavailable</td></tr>';
            if (badge) badge.textContent = '—';
        }
    }
}

async function loadAlerts() {
    const tbody = $('#alerts-body');
    if (!tbody) return;
    const badge = $('#alerts-badge');
    try {
        const data = await fetchJSON(`${API_BASE}/v1/alerts`);
        const alerts = data.alerts || [];
        if (badge) badge.textContent = alerts.length;

        if (alerts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">No active alerts</td></tr>';
        } else {
            tbody.innerHTML = alerts.map((a) => {
                const dir = (a.direction || '').toUpperCase();
                const dirClass = dir === 'ABOVE' ? 'dir-buy' : 'dir-sell';
                const dirLabel = dir === 'ABOVE' ? 'Price ≥' : 'Price ≤';
                return `<tr>
                    <td><strong>${a.epic || '—'}</strong></td>
                    <td class="${dirClass}">${dirLabel}</td>
                    <td class="mono">${a.threshold != null ? fmt.number(Number(a.threshold)) : '—'}</td>
                    <td><span class="channel-tag">${a.notification_channel || '—'}</span></td>
                    <td class="mono">${fmt.date(a.created_at)}</td>
                </tr>`;
            }).join('');
        }
        hasAlerts = true;
        sectionTime('alerts-ts');
    } catch (e) {
        console.warn('Alerts unavailable:', e.message);
        if (!hasAlerts) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">Alerts unavailable</td></tr>';
            if (badge) badge.textContent = '—';
        }
    }
}

async function loadStats() {
    try {
        const data = await fetchJSON(`${API_BASE}/dashboard/transactions`);
        const all = data.transactions || [];
        const trades = all.filter(t => t.transactionType === 'TRADE').map(t => ({ ...t, size: parseFloat(t.size) || 0 }));

        const total = trades.length;
        const wins = trades.filter(t => t.size > 0);
        const losses = trades.filter(t => t.size < 0);
        const winCount = wins.length;
        const lossCount = losses.length;

        const grossWin = wins.reduce((s, t) => s + t.size, 0);
        const grossLoss = Math.abs(losses.reduce((s, t) => s + t.size, 0));
        const profitFactor = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0);
        const winRate = total > 0 ? (winCount / total) * 100 : 0;
        const avgWin = winCount > 0 ? grossWin / winCount : 0;
        const avgLoss = lossCount > 0 ? grossLoss / lossCount : 0;
        const bestTrade = wins.length > 0 ? Math.max(...wins.map(t => t.size)) : 0;
        const worstTrade = losses.length > 0 ? Math.min(...losses.map(t => t.size)) : 0;

        let consecWins = 0, consecLosses = 0, maxWins = 0, maxLosses = 0;
        for (const t of trades) {
            if (t.size > 0) { consecWins++; consecLosses = 0; if (consecWins > maxWins) maxWins = consecWins; }
            else if (t.size < 0) { consecLosses++; consecWins = 0; if (consecLosses > maxLosses) maxLosses = consecLosses; }
        }

        const s = (id) => $(`#stat-${id}`);
        const set = (id, val) => { const el = s(id); if (el) el.textContent = val; };

        set('total-trades', total);
        set('win-rate', total > 0 ? winRate.toFixed(1) + '%' : '—');

        const pfEl = s('profit-factor');
        if (pfEl) pfEl.textContent = profitFactor === Infinity ? '∞' : (profitFactor > 0 ? profitFactor.toFixed(2) : '—');

        const setVal = (id, val, cls) => {
            const el = s(id);
            if (el) { el.textContent = val; el.className = 'stat-value' + (cls ? ' ' + cls : ''); }
        };

        setVal('avg-win', avgWin > 0 ? fmt.currency(avgWin) : '—', 'positive');
        setVal('avg-loss', avgLoss > 0 ? fmt.currency(avgLoss) : '—', 'negative');
        setVal('best-trade', bestTrade > 0 ? fmt.currency(bestTrade) : '—', 'positive');
        setVal('worst-trade', worstTrade < 0 ? fmt.currency(Math.abs(worstTrade)) : '—', 'negative');
        set('consec-wins', maxWins || '—');
        set('consec-losses', maxLosses || '—');

        hasStats = true;
        sectionTime('stats-ts');
    } catch (e) {
        console.warn('Stats unavailable:', e.message);
        if (!hasStats) {
            document.querySelectorAll('.stat-value').forEach(el => { el.textContent = '—'; el.className = 'stat-value'; });
        }
    }
}

async function loadSentiment() {
    for (const epic of TICKER_EPICS) {
        try {
            const data = await fetchJSON(`${API_BASE}/v1/accounts/client-sentiment?epic=${epic}`);
            const longPct = data.longPositionPercentage;
            const shortPct = data.shortPositionPercentage;

            const bar = $(`#sentiment-${epic}-bar`);
            const longEl = $(`#sentiment-${epic}-long`);
            const shortEl = $(`#sentiment-${epic}-short`);

            if (bar && longPct != null) bar.style.width = longPct + '%';
            if (longEl && longPct != null) longEl.textContent = longPct.toFixed(1) + '%';
            if (shortEl && shortPct != null) shortEl.textContent = shortPct.toFixed(1) + '%';
        } catch (e) {
            console.warn(`Sentiment ${epic} unavailable:`, e.message);
        }
    }
}

async function refreshAll() {
    const btn = $('#btn-refresh');
    if (btn) btn.classList.add('spinning');
    await Promise.all([loadPortfolio(), loadPositions(), loadActivity(), loadOrders(), loadTickers(), loadStats(), loadAlerts(), loadSparklines(), loadSentiment()]);
    if (btn) btn.classList.remove('spinning');
}

document.addEventListener('DOMContentLoaded', async () => {
    const btn = $('#btn-refresh');
    if (btn) btn.addEventListener('click', refreshAll);

    await loadSettings();
    await refreshAll();
    connectPriceStream();

    setInterval(loadPositions, REFRESH_POSITIONS_MS);
    setInterval(loadPortfolio, REFRESH_EQUITY_MS);
    setInterval(loadActivity, REFRESH_ACTIVITY_MS);
    setInterval(loadOrders, REFRESH_ORDERS_MS);
    setInterval(loadTickers, REFRESH_TICKERS_MS);
    setInterval(loadStats, REFRESH_STATS_MS);
    setInterval(loadAlerts, 60000);
    setInterval(loadSparklines, 60000);
    setInterval(loadSentiment, 60000);
    setInterval(updateClock, 5000);
});
