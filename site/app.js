/* Liqmap Chart — interactive chart for the liqmap-data repo. Data comes from data.json (built by site/build.py). */
(async function () {
const loadingEl = document.getElementById("loading");
let DATA;
try {
  const res = await fetch("data.json", { cache: "no-cache" });
  if (!res.ok) throw new Error("HTTP " + res.status);
  DATA = await res.json();
} catch (e) {
  loadingEl.textContent = "Could not load the data (" + e.message + "). Reload the page; if it keeps failing, check the site workflow in the repo's Actions tab.";
  return;
}
const WIB = 25200;
const TFS = [["1m",60],["5m",300],["15m",900],["1h",3600],["4h",14400],["1D",86400],["1W",604800],["1M",2592000]];
const RANGES = [["1D",1],["1W",7],["1M",30],["1Y",365],["All",0]];
// 1D / 1W / 1M come from hist/<coin>_<tf>.json: Binance public archive since 2020 + this repo, heatmap precomputed by
// site/build_history.py with a window of one candle: 1D = 24 h (model v6 as checked against CoinGlass), 1W = 7 days, 1M = 30 days.
const HIST = { 86400: "1D", 604800: "1W", 2592000: "1M" };
const WIN_TXT = { 86400: "24 hours", 604800: "7 days", 2592000: "30 days" };
const MIN_ROW_PX = 3;   // merge price boxes until each heatmap row is at least this many pixels tall
const LUT = (() => { // viridis, 256 steps
  const st = [[0,[68,1,84]],[.25,[59,82,139]],[.5,[33,145,140]],[.75,[94,201,98]],[1,[253,231,37]]], out = [];
  for (let i = 0; i < 256; i++) { const t = i / 255; let k = 0; while (k < st.length - 2 && t > st[k + 1][0]) k++;
    const [t0, a] = st[k], [t1, b] = st[k + 1], f = (t - t0) / (t1 - t0);
    out.push(`rgb(${a.map((v, j) => Math.round(v + (b[j] - v) * f)).join(",")})`); }
  return out; })();
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const usd = v => { const a = Math.abs(v); return a >= 1e9 ? "$" + (a / 1e9).toFixed(2) + "B" : a >= 1e6 ? "$" + (a / 1e6).toFixed(2) + "M" : a >= 1e3 ? "$" + (a / 1e3).toFixed(1) + "K" : "$" + Math.round(a); };
const qty = v => { const a = Math.abs(v); return a >= 1e6 ? (a / 1e6).toFixed(2) + "M" : a >= 1e3 ? (a / 1e3).toFixed(1) + "K" : a.toFixed(1); };
const dec = s => s === "ETHUSDT" ? 2 : 1;
const fmtP = (v, s) => v.toLocaleString("en-US", { minimumFractionDigits: dec(s), maximumFractionDigits: dec(s) });
const fmtT = t => { const d = new Date(t * 1000); const p = n => String(n).padStart(2, "0");
  return `${p(d.getUTCDate())} ${d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" })} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`; };

const state = { coin: "BTCUSDT", tf: 900, heat: true, map: true, thr: 0.6, hover: null, hoverPrice: null };
try { const s = JSON.parse(localStorage.getItem("liqmap-ui") || "{}"); Object.assign(state, s); } catch (e) {}
const COINS = ["BTCUSDT", "ETHUSDT"];
const stores = {};
let bars = [], store = null;

// ---------- data per interval ----------
const hist = {};   // coin|tf -> { bars, store }
function getStore(coin) { // 24-hour model on the 5-minute data of the last weeks, computed in the browser (intervals below 1D)
  const key = coin + "|288";
  if (!stores[key]) { const c = DATA[coin].c5; stores[key] = LiqModel.build(c, LiqModel.binsFor(c.c[c.c.length - 1]), 288);
    stores[key].tAt = s => c.t[s] + 300; }
  return stores[key];
}
async function loadHist(coin, tf) {
  const key = coin + "|" + tf; if (hist[key]) return hist[key];
  const res = await fetch(`hist/${coin}_${tf}.json`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`hist/${coin}_${tf}.json: HTTP ${res.status}`);
  const H = await res.json(), n = H.t.length, sn = H.snap, m = sn.b.length;
  const start = Int32Array.from(sn.start), bins = new Int32Array(m), lv = new Float32Array(m), sv = new Float32Array(m), colMax = new Float32Array(n);
  for (let i = 0; i < n; i++) {           // bins are stored as differences inside each snapshot; USD in thousands
    let b = 0;
    for (let q = start[i]; q < start[i + 1]; q++) { b = q === start[i] ? sn.b[q] : b + sn.b[q]; bins[q] = b; lv[q] = sn.L[q] * 1000; sv[q] = sn.S[q] * 1000;
      if (lv[q] + sv[q] > colMax[i]) colMax[i] = lv[q] + sv[q]; }
  }
  const st = { B: { w: H.B[0], off: H.B[1], dx: H.B[2] }, first: 0, n, start, bins, lv, sv, colMax, tAt: s => H.tclose[s] };
  return (hist[key] = { H, store: st });
}
function liqBuckets(L, opens) { // sum actual liquidations into bars given by their open times (any interval)
  const n = opens.length, sumL = new Float64Array(n), sumS = new Float64Array(n);
  let j = 0;
  for (let i = 0; i < L.t.length; i++) {
    const t = L.t[i]; if (t < opens[0]) continue;
    while (j + 1 < n && opens[j + 1] <= t) j++;
    sumL[j] += L.l[i]; sumS[j] += L.s[i];
  }
  let firstBar = n;
  if (L.first != null) { firstBar = 0; while (firstBar + 1 < n && opens[firstBar + 1] <= L.first) firstBar++; if (opens[firstBar] > L.first) firstBar = 0; }
  return { sumL, sumS, firstBar };
}
function premAvg(P, a, b) { // mean of a regular series P = {t0, step, p[]} over open times in [a, b); null if none
  if (!P) return null;
  let i0 = Math.max(0, Math.ceil((a - P.t0) / P.step)), i1 = Math.min(P.p.length, Math.ceil((b - P.t0) / P.step)), s = 0, n = 0;
  for (let i = i0; i < i1; i++) { const v = P.p[i]; if (v != null) { s += v; n++; } }
  return n ? s / n : null;
}
function volSum(S, a, b) { // [volume, taker-buy volume] summed over 5-minute values with open time in [a, b); null if none
  if (!S) return null;
  let i0 = Math.max(0, Math.ceil((a - S.t0) / S.step)), i1 = Math.min(S.v.length, Math.ceil((b - S.t0) / S.step)), v = 0, tb = 0, n = 0;
  for (let i = i0; i < i1; i++) if (S.v[i] != null && S.tb[i] != null) { v += S.v[i]; tb += S.tb[i]; n++; }
  return n ? [v, tb] : null;
}
function lastVal(S, key, a, b) { // last non-null value of S[key] with open time in [a, b)
  if (!S || !S[key]) return null;
  for (let i = Math.min(S[key].length, Math.ceil((b - S.t0) / S.step)) - 1, i0 = Math.max(0, Math.ceil((a - S.t0) / S.step)); i >= i0; i--) if (S[key][i] != null) return S[key][i];
  return null;
}
function keySum(S, key, a, b) {
  if (!S || !S[key]) return null;
  let i0 = Math.max(0, Math.ceil((a - S.t0) / S.step)), i1 = Math.min(S[key].length, Math.ceil((b - S.t0) / S.step)), s = 0, n = 0;
  for (let i = i0; i < i1; i++) if (S[key][i] != null) { s += S[key][i]; n++; }
  return n ? s : null;
}
const US_V = ["coinbase", "kraken", "gemini"], NU_V = ["binance", "bybit", "okx", "bithumb", "upbit"], FUT_V = ["bybit", "okx"];
const VNAME = { coinbase: "Coinbase", kraken: "Kraken", gemini: "Gemini", binance: "Binance", bybit: "Bybit", okx: "OKX", bithumb: "Bithumb", upbit: "Upbit" };
const CROWD = {};   // coin -> hist/<coin>_crowd.json (account long/short ratios + 30-day statistics), loaded at start
function addPrem(coin, out, tf) { // per bar: Coinbase premium and Binance long/short ratios, averaged over the bar
  const P = DATA[coin].prem || {}, src = HIST[tf] ? P.d1 : P.m5, C = CROWD[coin] && CROWD[coin].m5;
  const A = C && { t0: C.t0, step: C.step, p: C.acc }, T = C && { t0: C.t0, step: C.step, p: C.top };
  out.forEach((r, i) => { const end = i + 1 < out.length ? out[i + 1].b : r.b + (HIST[tf] ? Math.max(tf, 86400) : tf);
    const a = tf === 60 ? Math.floor(r.b / 300) * 300 : r.b, b = tf === 60 ? a + 300 : end;
    r.prem = premAvg(src, a, b);
    // other venues (collector/markets.py, collector/spot.py): 5-minute values below 1D, daily values on 1D/1W/1M
    const M = DATA[coin].mk || {}, Hh = !!HIST[tf], S5 = M.spot5 || {}, SD = M.spotd || {}, F5 = M.fut5 || {}, FD = M.futd || {};
    r.sv = {}; r.us = r.nu = r.fu = r.oiX = r.lqL = r.lqS = null;
    if (tf !== 60) {           // spot and futures volumes are 5-minute values: not split further on 1m
      // on 1D/1W/1M the newest (unfinished) day has no daily value yet: fall back to its 5-minute values
      for (const v of US_V.concat(NU_V)) { const x = Hh ? (SD[v] ? volSum(SD[v], a, b) || volSum(S5[v], Math.max(a, SD[v].t0 + SD[v].step * SD[v].v.length), b) : null) : volSum(S5[v], a, b); if (x) r.sv[v] = x; }
      const grp = vs => { let v = 0, t = 0, n = 0; for (const k of vs) if (r.sv[k]) { v += r.sv[k][0]; t += r.sv[k][1]; n++; } return n ? [v, t] : null; };
      r.us = grp(US_V); r.nu = grp(NU_V);
      if (!Hh) { const parts = [volSum((DATA[coin].spot || {}).fu, a, b)].concat(FUT_V.map(v => volSum(F5[v], a, b))).filter(Boolean);
        r.fu = parts.length === 3 ? [parts.reduce((s, x) => s + x[0], 0), parts.reduce((s, x) => s + x[1], 0)] : null;
        const l = FUT_V.map(v => keySum(F5[v], "l", a, b)), sh = FUT_V.map(v => keySum(F5[v], "s", a, b));
        if (l.every(x => x != null)) { r.lqL = l[0] + l[1]; r.lqS = sh[0] + sh[1]; } }
      const ois = FUT_V.map(v => Hh ? (lastVal(F5[v], "oi", a, b) ?? lastVal(FD[v], "oi", a, b)) : lastVal(F5[v], "oi", a, b));
      if (ois.every(x => x != null)) r.oiX = ois[0] + ois[1];
    }
    r.fund = Hh ? (premAvg(M.fundd, a, b) ?? premAvg(M.fund1h, a, b)) : premAvg(M.fund1h, a, b);
    if (r.fund == null && !Hh && M.fund1h) r.fund = lastVal(M.fund1h, "p", a - 3 * 3600, b);   // current hour not stored yet: last known
    if (!Hh) r.bas = premAvg(M.bas5, a, b);
    else { const sc = lastVal(SD.binance, "c", a, b); r.basSpot = sc; r.bas = sc ? null : premAvg(M.bas5, a, b); }
    if (!HIST[tf]) { r.lsr = premAvg(A, a, b); r.tpr = premAvg(T, a, b); } });
  return out;
}
function buildBars(coin, tf) {
  const D = DATA[coin];
  if (HIST[tf]) {
    const { H, store: st } = hist[coin + "|" + HIST[tf]];
    store = st;
    const q = liqBuckets(D.l5, H.t);
    return addPrem(coin, H.t.map((t, i) => ({ b: t, o: H.o[i], h: H.h[i], l: H.l[i], c: H.c[i], v: H.v[i], oi: H.oi[i],
      snap: st.start[i + 1] > st.start[i] ? i : -1, liqL: q.sumL[i], liqS: q.sumS[i], hasLiq: i >= q.firstBar, time: t + WIB,
      lsr: H.lsr ? H.lsr[i] : null, tpr: H.tpr ? H.tpr[i] : null })), tf);
  }
  const c5 = D.c5, src = tf === 60 ? D.c1 : c5, L = tf === 60 ? D.l1 : D.l5;
  const out = [];
  let cur = null;
  for (let i = 0; i < src.t.length; i++) {
    const t = src.t[i], b = Math.floor(t / tf) * tf;
    if (!cur || cur.b !== b) { cur = { b, o: src.o[i], h: src.h[i], l: src.l[i], c: src.c[i], v: 0, oi: null, snap: -1 }; out.push(cur); }
    cur.h = Math.max(cur.h, src.h[i]); cur.l = Math.min(cur.l, src.l[i]); cur.c = src.c[i]; cur.v += src.v[i] || 0;
    // open interest at the bar's close: 5-minute data stores OI at the START of each candle, so the close value is
    // the next candle's (checked: Coinalyze close(t) vs open(t+5m), median difference 0.0008%); 1-minute data stores the close
    const oiClose = tf === 60 ? src.oi[i] : (i + 1 < src.t.length && src.oi[i + 1] != null ? src.oi[i + 1] : src.oi[i]);
    if (oiClose != null) cur.oi = oiClose;
    // heatmap column = state at the close of the latest 5-minute candle that has closed by this bar's close
    cur.snap = tf === 60 ? Math.floor((t + 60 - 300 - c5.t[0]) / 300) : i;
  }
  store = getStore(coin);
  const q = liqBuckets(L, out.map(r => r.b));
  out.forEach((r, i) => { if (!(r.snap >= store.first && r.snap < store.n)) r.snap = -1;
    r.liqL = q.sumL[i]; r.liqS = q.sumS[i]; r.hasLiq = i >= q.firstBar; r.time = r.b + WIB; });
  return addPrem(coin, out, tf);
}
function finishBas(bars) { bars.forEach(r => { if (r.basSpot) r.bas = (r.c / r.basSpot - 1) * 100; }); return bars; }

// ---------- chart ----------
const LC = LightweightCharts;
const chart = LC.createChart(document.getElementById("chart"), {
  autoSize: true,
  layout: { background: { type: "solid", color: css("--panel") }, textColor: css("--muted"), fontFamily: css("--font-ui"), fontSize: 11, panes: { separatorColor: css("--line"), separatorHoverColor: "#2b3240" } },
  grid: { vertLines: { color: "rgba(255,255,255,0.035)" }, horzLines: { color: "rgba(255,255,255,0.035)" } },
  crosshair: { mode: LC.CrosshairMode.Normal, vertLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" }, horzLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" } },
  rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: true, secondsVisible: false, rightOffset: 6, minBarSpacing: 0.05 },
  localization: { timeFormatter: t => fmtT(t) + " WIB" },
});
const candles = chart.addSeries(LC.CandlestickSeries, { upColor: css("--up"), downColor: css("--down"), borderUpColor: css("--up"), borderDownColor: css("--down"), wickUpColor: css("--up"), wickDownColor: css("--down"), priceLineColor: "#9aa3b5", priceLineStyle: 2 }, 0);
// RSI pane (pane 1): 14-period RSI (Wilder) of the shown candles, with regular divergences marked
const rsiS = chart.addSeries(LC.LineSeries, { color: css("--c4"), lineWidth: 1.5, priceFormat: { type: "custom", formatter: v => v.toFixed(1), minMove: 0.1 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3, autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) }, 1);
for (const [v, st] of [[70, 2], [30, 2], [50, 3]]) rsiS.createPriceLine({ price: v, color: "#3a4150", lineWidth: 1, lineStyle: st, axisLabelVisible: false });
rsiS.priceScale().applyOptions({ scaleMargins: { top: 0.06, bottom: 0.04 } });
const rsiMarks = LC.createSeriesMarkers(rsiS, []);
const fmtUsd = { type: "custom", formatter: v => usd(v), minMove: 1 };
const liqS = chart.addSeries(LC.HistogramSeries, { color: css("--short"), priceFormat: fmtUsd, lastValueVisible: false, priceLineVisible: false, base: 0 }, 2);
const liqL = chart.addSeries(LC.HistogramSeries, { color: css("--long"), priceFormat: fmtUsd, lastValueVisible: false, priceLineVisible: false, base: 0 }, 2);
const oiS = chart.addSeries(LC.LineSeries, { color: css("--oi"), lineWidth: 2, priceFormat: { type: "custom", formatter: qty, minMove: 0.001 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 3);
const volS = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "custom", formatter: qty, minMove: 0.001 }, lastValueVisible: false, priceLineVisible: false }, 4);
const fmtPrem = v => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(3) + "%";
const premS = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "custom", formatter: fmtPrem, minMove: 0.0001 }, lastValueVisible: false, priceLineVisible: false, base: 0 }, 5);
const fmtR = v => v.toFixed(2);
const lsrA = chart.addSeries(LC.LineSeries, { color: css("--c4"), lineWidth: 2, priceFormat: { type: "custom", formatter: fmtR, minMove: 0.001 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 6);
const lsrT = chart.addSeries(LC.LineSeries, { color: css("--c2"), lineWidth: 2, priceFormat: { type: "custom", formatter: fmtR, minMove: 0.001 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 6);
lsrA.createPriceLine({ price: 1, color: "#3a4150", lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
const fmtNet = v => (v > 0 ? "+" : v < 0 ? "−" : "") + qty(v);
const cvdUS = chart.addSeries(LC.LineSeries, { color: css("--c1"), lineWidth: 2, priceFormat: { type: "custom", formatter: fmtNet, minMove: 0.01 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 7);
const cvdNU = chart.addSeries(LC.LineSeries, { color: css("--c2"), lineWidth: 2, priceFormat: { type: "custom", formatter: fmtNet, minMove: 0.01 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 7);
cvdUS.createPriceLine({ price: 0, color: "#3a4150", lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
const fmtPct = d => v => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + "%";
const fundS = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "custom", formatter: fmtPct(4), minMove: 0.0001 }, lastValueVisible: false, priceLineVisible: false, base: 0 }, 8);
const basS = chart.addSeries(LC.LineSeries, { color: css("--fg"), lineWidth: 1.5, priceFormat: { type: "custom", formatter: fmtPct(3), minMove: 0.0001 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 8);
const panes = chart.panes();
[5, 1.25, 1.3, 1.1, 0.8, 0.9, 0.9, 1.1, 1].forEach((f, i) => panes[i] && panes[i].setStretchFactor(f));

// heatmap + liquidation-map primitive on the candle series
const heat = {
  _req: null, _views: null,
  attached(p) { this._req = p.requestUpdate; },
  detached() { this._req = null; },
  update() { this._req && this._req(); },
  updateAllViews() {},
  paneViews() {
    if (!this._views) this._views = [
      { zOrder: () => "bottom", renderer: () => ({ draw: tg => drawHeat(tg) }) },
      { zOrder: () => "bottom", renderer: () => ({ draw: tg => drawMap(tg) }) }, // under the candles, over the heatmap
    ];
    return this._views;
  },
};
candles.attachPrimitive(heat);

function yMap() { // price -> media y is linear on a normal scale
  const p0 = candles.coordinateToPrice(0), p1 = candles.coordinateToPrice(100);
  if (p0 == null || p1 == null || p0 === p1) return null;
  const k = 100 / (p1 - p0); return { y: p => (p - p0) * k, p0, k };
}
// Price boxes are 0.0744% tall (CoinGlass box size). When zoomed out they become thinner than a pixel and the
// heatmap turns into noise, so boxes are merged in groups of k (USD added up) until a row is >= MIN_ROW_PX tall.
function rowFactor(ym) { const px = Math.abs(store.B.w * ym.k); return Math.max(1, Math.ceil(MIN_ROW_PX / Math.max(px, 1e-6))); }
function eachRow(s, k, rLo, rHi, fn) { // fn(row, longUSD, shortUSD), rows in ascending order
  const st = store; let R = null, l = 0, sh = 0;
  for (let q = st.start[s]; q < st.start[s + 1]; q++) {
    const r = Math.floor(st.bins[q] / k); if (r < rLo || r > rHi) continue;
    if (r !== R) { if (R !== null) fn(R, l, sh); R = r; l = 0; sh = 0; }
    l += st.lv[q]; sh += st.sv[q];
  }
  if (R !== null) fn(R, l, sh);
}
function rowRange(Hm, k) {
  const B = store.B, pTop = candles.coordinateToPrice(0), pBot = candles.coordinateToPrice(Hm);
  return [Math.floor((pBot - B.off) / (B.w * k)) - 1, Math.floor((pTop - B.off) / (B.w * k)) + 1];
}
function drawHeat(target) {
  if (!state.heat || !bars.length) return;
  const B = store.B, ts = chart.timeScale(), vr = ts.getVisibleLogicalRange(), ym = yMap();
  if (!vr || !ym) return;
  const k = rowFactor(ym), RW = B.w * k;
  target.useBitmapCoordinateSpace(sc => {
    const ctx = sc.context, hr = sc.horizontalPixelRatio, vrt = sc.verticalPixelRatio, Hm = sc.mediaSize.height;
    const i0 = Math.max(0, Math.floor(vr.from) - 1), i1 = Math.min(bars.length - 1, Math.ceil(vr.to) + 1);
    if (i1 < i0) return;
    const x0 = ts.logicalToCoordinate(i0), x1 = ts.logicalToCoordinate(i0 + 1);
    const sp = Math.max(0.01, x1 - x0), stride = Math.max(1, Math.ceil(2 / sp));
    const [rLo, rHi] = rowRange(Hm, k);
    let vmax = 0;
    for (let i = i0; i <= i1; i++) { const s = bars[i].snap; if (s < 0) continue;
      eachRow(s, k, rLo, rHi, (r, l, sh) => { if (l + sh > vmax) vmax = l + sh; }); }
    if (vmax <= 0) return;
    vmax *= state.thr;
    for (let g = i0 - ((i0 % stride) + stride) % stride; g <= i1; g += stride) {
      const last = Math.min(g + stride - 1, bars.length - 1); if (last < 0) continue;
      const s = bars[last].snap; if (s < 0) continue;
      const xl = ts.logicalToCoordinate(Math.max(g, 0)) - sp / 2, xr = ts.logicalToCoordinate(last) + sp / 2;
      if (xl == null || xr == null) continue;
      const X = Math.round(xl * hr), W = Math.max(1, Math.round(xr * hr) - X);
      ctx.fillStyle = LUT[0]; ctx.fillRect(X, 0, W, Math.ceil(Hm * vrt));
      eachRow(s, k, rLo, rHi, (r, l, sh) => {
        const t = (l + sh) / vmax; if (t < 0.012) return;
        const yA = ym.y(B.off + (r + 1) * RW), yB = ym.y(B.off + r * RW);
        const Y = Math.round(yA * vrt), Hh = Math.max(1, Math.round(yB * vrt) - Y);
        ctx.fillStyle = LUT[Math.min(255, Math.floor(t * 255))]; ctx.fillRect(X, Y, W, Hh);
      });
    }
  });
}
function mapIndex() { const i = state.hover != null ? state.hover : bars.length - 1; return bars[i] && bars[i].snap >= 0 ? i : -1; }
function drawMap(target) {
  if (!state.map || !bars.length) return;
  const i = mapIndex(); if (i < 0) return;
  const B = store.B, s = bars[i].snap, ym = yMap(); if (!ym) return;
  const k = rowFactor(ym), RW = B.w * k;
  target.useBitmapCoordinateSpace(sc => {
    const ctx = sc.context, hr = sc.horizontalPixelRatio, vrt = sc.verticalPixelRatio, Wm = sc.mediaSize.width, Hm = sc.mediaSize.height;
    const [rLo, rHi] = rowRange(Hm, k);
    let mx = 0;
    eachRow(s, k, rLo, rHi, (r, l, sh) => { mx = Math.max(mx, l, sh); });
    if (mx <= 0) return;
    const maxW = Math.min(260, Wm * 0.26), right = Wm - 2;
    ctx.fillStyle = "rgba(11,13,17,0.45)"; ctx.fillRect(Math.round((right - maxW - 4) * hr), 0, Math.round((maxW + 6) * hr), Math.ceil(Hm * vrt));
    const cL = css("--long"), cS = css("--short");
    eachRow(s, k, rLo, rHi, (r, l, sh) => {
      const yA = ym.y(B.off + (r + 1) * RW), yB = ym.y(B.off + r * RW);
      const Y = Math.round(yA * vrt), Hh = Math.max(1, Math.round(yB * vrt) - Y - (yB - yA > 3 ? Math.round(vrt) : 0));
      for (const [v, col] of [[l, cL], [sh, cS]]) {
        if (v <= 0) continue; const w = Math.max(1, v / mx * maxW);
        ctx.fillStyle = col; ctx.fillRect(Math.round((right - w) * hr), Y, Math.round(w * hr), Hh);
      }
    });
    ctx.fillStyle = css("--muted"); ctx.font = `${Math.round(10 * vrt)}px ${css("--font-num")}`; ctx.textAlign = "right";
    // the map is the state at the moment shown (close of the bar's last 5-minute candle), not a sum over the bar
    ctx.fillText("Levels at " + fmtT(store.tAt(s) + WIB) + " WIB · max row " + usd(mx), Math.round(right * hr), Math.round((Hm - 6) * vrt));
  });
}

// ---------- legend ----------
const legend = document.getElementById("legend");
function binAt(i, price) { // heatmap row under the cursor (same merged rows as drawn)
  const B = store.B, s = bars[i] ? bars[i].snap : -1, ym = yMap(); if (s < 0 || price == null || !ym) return null;
  const k = rowFactor(ym), RW = B.w * k, r = Math.floor((price - B.off) / RW);
  let l = 0, sh = 0; eachRow(s, k, r, r, (_r, a, b) => { l = a; sh = b; });
  return { l, s: sh, low: B.off + r * RW, high: B.off + (r + 1) * RW };
}
function renderLegend() {
  if (!bars.length) return;
  const i = state.hover != null ? state.hover : bars.length - 1, r = bars[i], c = state.coin, chg = (r.c / r.o - 1) * 100;
  const cls = r.c >= r.o ? "pos" : "neg", tfName = TFS.find(x => x[1] === state.tf)[0];
  let heatTxt = "";
  if (state.hoverPrice != null && r.snap >= 0) { const h = binAt(i, state.hoverPrice);
    if (h) heatTxt = `<div class="row"><span><span class="k">Heat ${fmtP(h.low, c)}–${fmtP(h.high, c)}</span> ${usd(h.l + h.s)}</span>${h.l > 0 ? `<span class="lg">long ${usd(h.l)}</span>` : ""}${h.s > 0 ? `<span class="sh">short ${usd(h.s)}</span>` : ""}</div>`; }
  legend.innerHTML = `<div class="row"><span class="sym">${c.replace("USDT", "")}/USDT Perp · Binance · ${tfName}</span><span class="k">${fmtT(r.time)} WIB</span></div>
    <div class="row"><span><span class="k">O</span> <span class="${cls}">${fmtP(r.o, c)}</span></span><span><span class="k">H</span> <span class="${cls}">${fmtP(r.h, c)}</span></span><span><span class="k">L</span> <span class="${cls}">${fmtP(r.l, c)}</span></span><span><span class="k">C</span> <span class="${cls}">${fmtP(r.c, c)}</span></span><span class="${cls}">${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%</span></div>${heatTxt}`;
  const lp = document.getElementById("pl1"), op = document.getElementById("pl2"), vp = document.getElementById("pl3");
  lp.innerHTML = `<b>Actual liquidations</b>` + (r.hasLiq ? `<span class="sh">shorts ${usd(r.liqS)}</span> · <span class="lg">longs ${usd(r.liqL)}</span> <span class="k">Binance</span>` +
    (r.lqL != null ? ` · <span class="k">+ Bybit & OKX: shorts ${usd(r.lqS)}, longs ${usd(r.lqL)}</span>` : "") : `no data before ${fmtT(DATA[c][state.tf === 60 ? "l1" : "l5"].first + WIB)}`);
  op.innerHTML = `<b>Open interest</b>${r.oi != null ? "Binance " + qty(r.oi) + " " + c.replace("USDT", "") + " ≈ " + usd(r.oi * r.c) : "–"}` +
    (r.oi != null && r.oiX != null ? ` <span class="k">· Binance + Bybit + OKX ${qty(r.oi + r.oiX)} ≈ ${usd((r.oi + r.oiX) * r.c)}</span>` : "");
  vp.innerHTML = `<b>Volume</b>${qty(r.v)} ${c.replace("USDT", "")}`;
  const share = v => Math.round(v / (1 + v) * 100);
  document.getElementById("pl5").innerHTML = `<b>Long vs short</b>` + (r.lsr != null || r.tpr != null ?
    (r.lsr != null ? `<span class="ca">all accounts ${r.lsr.toFixed(2)}</span> <span class="k">(${share(r.lsr)}% of accounts long)</span>` : "") +
    (r.tpr != null ? ` · <span class="cb">big accounts ${r.tpr.toFixed(2)}</span> <span class="k">(by position size)</span>` : "") : "no data for this candle");
  const net = x => 2 * x[1] - x[0], cu = c.replace("USDT", ""), vs = window.__venues || [];
  const part = (lab, x, cls) => x ? `<span class="${cls}">${lab} ${fmtNet(net(x))}</span> <span class="k">of ${qty(x[0])} (${Math.round(x[1] / x[0] * 100)}% buys)</span>` : `<span class="k">${lab} –</span>`;
  const list = g => g.filter(v => vs.includes(v)).map(v => r.sv && r.sv[v] ? `${VNAME[v]} ${fmtNet(net(r.sv[v]))}` : `${VNAME[v]} –`).join(", ");
  document.getElementById("pl6").innerHTML = `<b>Spot net buying</b>` + (state.tf === 60 ? `<span class="k">5-minute data: use 5m or above</span>` :
    part("US", r.us, "pp") + ` <span class="k">(${list(US_V)})</span> · ` + part("non-US", r.nu, "cb") + ` <span class="k">(${list(NU_V)})</span>` +
    (r.fu ? " · " + part("futures, Binance+Bybit+OKX", r.fu, "k") : "") + ` <span class="k">${cu}, this candle</span>`);
  document.getElementById("pl7").innerHTML = `<b>Futures vs spot · funding</b>` +
    (r.bas != null ? `<span>futures ${fmtPct(3)(r.bas)} vs spot</span> <span class="k">(Binance)</span>` : `<span class="k">gap –</span>`) + " · " +
    (r.fund != null ? `<span class="${r.fund >= 0 ? "cb" : "ca"}">funding ${fmtPct(4)(r.fund)}</span> <span class="k">per 8h, avg Binance/Bybit/OKX: ${r.fund >= 0 ? "longs pay shorts" : "shorts pay longs"}</span>` : `<span class="k">funding –</span>`);
  rsiLabel(i);
  const pr = document.getElementById("pl4"), P = DATA[c].prem;
  pr.innerHTML = `<b>Coinbase premium</b>` + (r.prem != null ? `<span class="${r.prem >= 0 ? "pp" : "pn"}">${fmtPrem(r.prem)}</span> <span class="k">${r.prem >= 0 ? "Coinbase pricier: US buyers more eager" : "Coinbase cheaper: US sellers more eager"}</span>`
    : (() => { const S = P && P[HIST[state.tf] ? "d1" : "m5"]; return !S ? "no data" : r.b < S.t0 ? "no data before " + fmtT(S.t0 + WIB) : "not available for this candle yet"; })());
}
function placeLabels() {
  let y = 0; const ids = ["plR", "pl1", "pl2", "pl3", "pl4", "pl5", "pl6", "pl7"];
  for (let p = 0; p < 9; p++) { const h = chart.paneSize(p).height; if (p > 0) document.getElementById(ids[p - 1]).style.top = (y + 5) + "px"; y += h + 1; }
}
chart.subscribeCrosshairMove(p => {
  const i = (p && p.logical != null && p.point) ? Math.round(p.logical) : null;
  state.hover = (i != null && i >= 0 && i < bars.length) ? i : null;
  state.hoverPrice = (state.hover != null && p.paneIndex === 0 && p.point) ? candles.coordinateToPrice(p.point.y) : null;
  renderLegend(); if (state.map) heat.update();
});

// ---------- RSI and divergences ----------
// RSI = Relative Strength Index (J. Welles Wilder, 1978), 14 candles, Wilder smoothing, on the candles shown.
// 70 or more = strong recent buying ("overbought"), 30 or less = strong recent selling ("oversold").
// Divergence, same rules as TradingView's built-in "RSI Divergence Indicator": an RSI turning point is a low (high) below
// (above) the 5 candles on each side; it is compared with the previous turning point 5 to 60 candles earlier.
//   bullish: price makes a lower low but RSI makes a higher low  -> selling is losing force
//   bearish: price makes a higher high but RSI makes a lower high -> buying is losing force
// A turning point is only known 5 candles after it happens, so each divergence appears 5 candles late.
const RSI_N = 14, PIV = 5, DIV_MIN = 5, DIV_MAX = 60, DIV_LINES = 40;
function rsiCalc(c) {
  const n = c.length, out = new Array(n).fill(null); if (n <= RSI_N) return out;
  let g = 0, l = 0;
  for (let i = 1; i <= RSI_N; i++) { const d = c[i] - c[i - 1]; if (d > 0) g += d; else l -= d; }
  g /= RSI_N; l /= RSI_N; out[RSI_N] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  for (let i = RSI_N + 1; i < n; i++) {
    const d = c[i] - c[i - 1];
    g = (g * (RSI_N - 1) + Math.max(d, 0)) / RSI_N; l = (l * (RSI_N - 1) + Math.max(-d, 0)) / RSI_N;
    out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  }
  return out;
}
function rsiDivergences(B, r) { // -> [{type, i1, i2, conf}] ; conf = candle index where it becomes known (i2 + PIV)
  const pivot = (i, lowSide) => {
    if (r[i] == null || i < PIV || i + PIV >= r.length) return false;
    for (let k = 1; k <= PIV; k++) {
      const a = r[i - k], b = r[i + k]; if (a == null || b == null) return false;
      if (lowSide ? (a <= r[i] || b < r[i]) : (a >= r[i] || b > r[i])) return false;
    }
    return true;
  };
  const out = []; let pl = null, ph = null;
  for (let i = 0; i < r.length; i++) {
    if (pivot(i, true)) {
      if (pl != null && i - pl >= DIV_MIN && i - pl <= DIV_MAX && B[i].l < B[pl].l && r[i] > r[pl]) out.push({ type: "bull", i1: pl, i2: i, conf: i + PIV });
      pl = i;
    }
    if (pivot(i, false)) {
      if (ph != null && i - ph >= DIV_MIN && i - ph <= DIV_MAX && B[i].h > B[ph].h && r[i] < r[ph]) out.push({ type: "bear", i1: ph, i2: i, conf: i + PIV });
      ph = i;
    }
  }
  return out;
}
const divPool = []; // pairs of 2-point line series (RSI pane + price pane) reused across redraws
function divLine(k) {
  if (!divPool[k]) {
    const o = { lineWidth: 1.5, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, pointMarkersVisible: false, autoscaleInfoProvider: () => null };
    divPool[k] = [chart.addSeries(LC.LineSeries, o, 1), chart.addSeries(LC.LineSeries, { ...o, lineStyle: 2 }, 0)];
  }
  return divPool[k];
}
let rsiVals = [], rsiDivs = [];
function drawRsi() {
  rsiVals = rsiCalc(bars.map(r => r.c));
  rsiS.setData(bars.map((r, i) => rsiVals[i] != null ? { time: r.time, value: rsiVals[i] } : { time: r.time }));
  rsiDivs = rsiDivergences(bars, rsiVals).filter(d => d.conf < bars.length);
  const bull = css("--c1"), bear = css("--c3");
  rsiMarks.setMarkers(rsiDivs.map(d => ({ time: bars[d.i2].time, position: d.type === "bull" ? "belowBar" : "aboveBar",
    color: d.type === "bull" ? bull : bear, shape: d.type === "bull" ? "arrowUp" : "arrowDown", size: 0.6 })));
  const recent = rsiDivs.slice(-DIV_LINES);
  for (let k = 0; k < Math.max(divPool.length, recent.length); k++) {
    const [lr, lp] = divLine(k), d = recent[k];
    if (!d) { lr.setData([]); lp.setData([]); continue; }
    const col = d.type === "bull" ? bull : bear, a = bars[d.i1], b = bars[d.i2];
    lr.applyOptions({ color: col }); lp.applyOptions({ color: col });
    lr.setData([{ time: a.time, value: rsiVals[d.i1] }, { time: b.time, value: rsiVals[d.i2] }]);
    lp.setData(d.type === "bull" ? [{ time: a.time, value: a.l }, { time: b.time, value: b.l }] : [{ time: a.time, value: a.h }, { time: b.time, value: b.h }]);
  }
}
function rsiLabel(i) {
  const v = rsiVals[i], c = state.coin;
  let last = null; for (let k = rsiDivs.length - 1; k >= 0; k--) if (rsiDivs[k].conf <= i) { last = rsiDivs[k]; break; }
  const zone = v == null ? "" : v >= 70 ? ` <span class="k">(70+: strong recent buying)</span>` : v <= 30 ? ` <span class="k">(30 or less: strong recent selling)</span>` : "";
  let dtxt = `<span class="k">no divergence yet in this view</span>`;
  if (last) {
    const a = bars[last.i1], b = bars[last.i2], bu = last.type === "bull", ago = i - last.i2;
    dtxt = `<span class="${bu ? "pp" : "pn"}">${bu ? "bullish" : "bearish"} divergence</span> <span class="k">at ${fmtT(b.time)} WIB (${ago} candle${ago === 1 ? "" : "s"} ago): price ${bu ? "low" : "high"} ${fmtP(bu ? a.l : a.h, c)} → ${fmtP(bu ? b.l : b.h, c)}, RSI ${rsiVals[last.i1].toFixed(1)} → ${rsiVals[last.i2].toFixed(1)}</span>`;
  }
  document.getElementById("plR").innerHTML = `<b>RSI 14</b>${v == null ? "–" : v.toFixed(1)}${zone} · ${dtxt}`;
}

// ---------- data loading / controls ----------
function setData(keepRange) {
  const prev = keepRange ? chart.timeScale().getVisibleRange() : null;
  bars = finishBas(buildBars(state.coin, state.tf));
  const up = css("--up"), dn = css("--down");
  candles.applyOptions({ priceFormat: { type: "price", precision: dec(state.coin), minMove: state.coin === "ETHUSDT" ? 0.01 : 0.1 } });
  candles.setData(bars.map(r => ({ time: r.time, open: r.o, high: r.h, low: r.l, close: r.c })));
  liqS.setData(bars.map(r => r.hasLiq ? { time: r.time, value: r.liqS } : { time: r.time }));
  liqL.setData(bars.map(r => r.hasLiq ? { time: r.time, value: -r.liqL } : { time: r.time }));
  oiS.setData(bars.map(r => r.oi != null ? { time: r.time, value: r.oi } : { time: r.time }));
  volS.setData(bars.map(r => ({ time: r.time, value: r.v, color: r.c >= r.o ? "rgba(238,241,245,0.35)" : "rgba(242,85,124,0.45)" })));
  const pPos = css("--c1"), pNeg = css("--c3");
  premS.setData(bars.map(r => r.prem != null ? { time: r.time, value: r.prem, color: r.prem >= 0 ? pPos : pNeg } : { time: r.time }));
  lsrA.setData(bars.map(r => r.lsr != null ? { time: r.time, value: r.lsr } : { time: r.time }));
  lsrT.setData(bars.map(r => r.tpr != null ? { time: r.time, value: r.tpr } : { time: r.time }));
  const fP = css("--c2"), fN = css("--c4");
  fundS.setData(bars.map(r => r.fund != null ? { time: r.time, value: r.fund, color: r.fund >= 0 ? fP : fN } : { time: r.time }));
  basS.setData(bars.map(r => r.bas != null ? { time: r.time, value: r.bas } : { time: r.time }));
  drawRsi();
  // running total of net aggressive spot buying (taker buy minus taker sell), per group. Both lines start at 0 on the
  // first bar where EVERY venue shown in this view has data, so the totals cover the same period and the same venues.
  const venues = US_V.concat(NU_V).filter(v => bars.some(r => r.sv && r.sv[v]));
  const from = venues.length ? Math.max(...venues.map(v => bars.findIndex(r => r.sv && r.sv[v]))) : -1;
  bars.forEach(r => { r.us = r.sv ? (US_V.filter(v => venues.includes(v)).every(v => r.sv[v]) ? r.us : null) : null; r.nu = r.sv ? (NU_V.filter(v => venues.includes(v)).every(v => r.sv[v]) ? r.nu : null) : null; });
  window.__venues = venues;
  let cu = 0, cn = 0;
  cvdUS.setData(bars.map((r, i) => { if (from < 0 || i < from || !r.us) return { time: r.time }; cu += 2 * r.us[1] - r.us[0]; return { time: r.time, value: cu }; }));
  cvdNU.setData(bars.map((r, i) => { if (from < 0 || i < from || !r.nu) return { time: r.time }; cn += 2 * r.nu[1] - r.nu[0]; return { time: r.time, value: cn }; }));
  if (prev) { try { chart.timeScale().setVisibleRange(prev); } catch (e) { applyRange(3); } }
  renderLegend(); heat.update(); requestAnimationFrame(placeLabels);
}
function applyRange(days) {
  const ts = chart.timeScale(); if (!bars.length) return;
  const last = bars[bars.length - 1].time;
  if (!days) { ts.setVisibleLogicalRange({ from: -1, to: bars.length - 1 + 6 }); return; }
  const from = Math.max(bars[0].time, last - days * 86400);
  ts.setVisibleRange({ from, to: last });
}
function save() { try { localStorage.setItem("liqmap-ui", JSON.stringify({ coin: state.coin, tf: state.tf, heat: state.heat, map: state.map, thr: state.thr })); } catch (e) {} }
function pressed() {
  for (const k of COINS) document.getElementById("coin-" + k).setAttribute("aria-pressed", k === state.coin);
  for (const [n, s] of TFS) document.getElementById("tf-" + n).setAttribute("aria-pressed", s === state.tf);
  document.getElementById("winlabel").textContent = WIN_TXT[state.tf] || "24 hours";
}
const tfBox = document.getElementById("tfs"), rgBox = document.getElementById("ranges");
for (const [n, s] of TFS) { const b = document.createElement("button"); b.className = "btn"; b.id = "tf-" + n; b.textContent = n;
  if (s === 60) b.title = "1-minute data covers only the last ~27 hours";
  if (HIST[s]) b.title = "History since 2020 (Binance public archive)";
  b.onclick = () => { state.tf = s; save(); pressed(); refresh(true); }; tfBox.appendChild(b); }
for (const [n, d] of RANGES) { const b = document.createElement("button"); b.className = "btn"; b.id = "rg-" + n; b.textContent = n;
  b.onclick = () => applyRange(d); rgBox.appendChild(b); }
for (const k of COINS) document.getElementById("coin-" + k).onclick = () => {
  if (k === state.coin) return; state.coin = k; save(); pressed(); refresh(true); };
const optHeat = document.getElementById("optHeat"), optMap = document.getElementById("optMap"), thr = document.getElementById("thr"), thrv = document.getElementById("thrv");
optHeat.checked = state.heat; optMap.checked = state.map; thr.value = state.thr; thrv.textContent = (+state.thr).toFixed(2);
optHeat.onchange = () => { state.heat = optHeat.checked; save(); heat.update(); };
optMap.onchange = () => { state.map = optMap.checked; save(); heat.update(); };
thr.oninput = () => { state.thr = +thr.value; thrv.textContent = state.thr.toFixed(2); save(); heat.update(); };
let busy = 0;
function refresh(keepRange, after) { // load what the interval needs (history file or browser calculation), then draw
  const el = document.getElementById("loading"), coin = state.coin, tf = state.tf, my = ++busy;
  const ready = HIST[tf] ? !!hist[coin + "|" + HIST[tf]] : !!stores[coin + "|288"];
  const go = () => { if (my !== busy) return; setData(keepRange); if (after) after(); el.hidden = true; };
  if (ready) { go(); return; }
  el.textContent = HIST[tf] ? "Loading history…" : "Calculating heatmap…"; el.hidden = false;
  setTimeout(async () => {
    try { if (HIST[tf]) await loadHist(coin, HIST[tf]); else getStore(coin); go(); }
    catch (e) { el.textContent = "Could not load this interval (" + e.message + "). Try another interval or reload."; }
  }, 30);
}
// ---------- US spot ETF flows (data/etf/<COIN>.csv from Farside, collected by collector/etf.py) ----------
const ETF = DATA.etf || {};
const fmtM = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + (Math.abs(v) >= 1000 ? "$" + (Math.abs(v) / 1000).toFixed(2) + "B" : "$" + Math.abs(v).toFixed(1) + "M");
const etfBox = document.getElementById("etf");
const etfChart = LC.createChart(document.getElementById("etfchart"), {
  autoSize: true,
  layout: { background: { type: "solid", color: css("--panel") }, textColor: css("--muted"), fontFamily: css("--font-ui"), fontSize: 11 },
  grid: { vertLines: { color: "rgba(255,255,255,0.035)" }, horzLines: { color: "rgba(255,255,255,0.035)" } },
  crosshair: { mode: LC.CrosshairMode.Magnet, vertLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" }, horzLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" } },
  rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: false, rightOffset: 2 },
  localization: { timeFormatter: t => fmtD(t) },
});
const etfS = etfChart.addSeries(LC.HistogramSeries, { priceFormat: { type: "custom", formatter: fmtM, minMove: 0.1 }, lastValueVisible: false, priceLineVisible: false, base: 0 });
let etfRange = 92;
function etfTable(i) {
  const E = ETF[state.coin]; if (!E) return;
  const n = E.t.length; if (i == null || i < 0 || i >= n) i = n - 1;
  const sum = k => { let s = 0; for (let j = Math.max(0, i - k + 1); j <= i; j++) s += E.total[j] || 0; return s; };
  const fund = E.cols.map(c => [c, E.v[c][i]]).filter(([, v]) => v != null && v !== 0).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const shown = fund.slice(0, 6), rest = fund.slice(6).reduce((s, x) => s + x[1], 0);
  document.getElementById("etfweek").textContent = `Flows on ${fmtD(E.t[i])}` + (i === n - 1 ? " (latest day)" : "") + " · US$";
  const row = (name, v, cls = "") => `<tr${cls ? ` class="${cls}"` : ""}><th scope="row">${name}</th><td class="strong ${v > 0 ? "pp" : v < 0 ? "pn" : ""}">${fmtM(v)}</td></tr>`;
  document.getElementById("etfbody").innerHTML =
    (shown.length ? shown.map(([c, v]) => row(c, v)).join("") : `<tr><th scope="row">No fund moved</th><td>–</td></tr>`) +
    (fund.length > 6 ? row(`${fund.length - 6} others`, rest) : "") +
    row("Total that day", E.total[i], "sum") + row("Last 5 trading days", sum(5), "sum") + row("Last 20 trading days", sum(20), "sum") +
    row("Since launch (" + fmtD(E.t[0]) + ")", sum(n), "sum");
}
function etfApplyRange() {
  const E = ETF[state.coin]; if (!E) return;
  const n = E.t.length, last = E.t[n - 1];
  let from = 0; if (etfRange) while (from < n - 1 && E.t[from] < last - etfRange * 86400) from++;
  requestAnimationFrame(() => etfChart.timeScale().setVisibleLogicalRange({ from: from - 0.5, to: n - 1 + 2 }));
  for (const b of document.querySelectorAll("#etfranges .btn")) b.setAttribute("aria-pressed", +b.dataset.d === etfRange);
}
function setEtf() {
  const E = ETF[state.coin];
  etfBox.hidden = !E; if (!E) return;
  const pos = css("--c1"), neg = css("--c3");
  etfS.setData(E.t.map((t, j) => E.total[j] != null ? { time: t, value: E.total[j], color: E.total[j] >= 0 ? pos : neg } : { time: t }));
  document.getElementById("etf-h").textContent = `US spot ${state.coin.replace("USDT", "") === "BTC" ? "Bitcoin" : "Ether"} ETF flows`;
  document.getElementById("etfasof").textContent = `Daily, US trading days · latest: ${fmtD(E.t[E.t.length - 1])} · a day's figures arrive after the US close (about 04:00 WIB) and can be revised the next day`;
  etfApplyRange(); etfTable();
}
for (const b of document.querySelectorAll("#etfranges .btn")) b.onclick = () => { etfRange = +b.dataset.d; etfApplyRange(); };
etfChart.subscribeCrosshairMove(p => { const E = ETF[state.coin]; if (!E) return; etfTable(p && p.time != null ? E.t.indexOf(p.time) : null); });
for (const k of COINS) document.getElementById("coin-" + k).addEventListener("click", setEtf);

// ---------- Crowd positioning: Binance account long/short ratio vs price 30 days later ----------
const crowdBox = document.getElementById("crowd");
function fifthOf(C, v) { let k = 0; while (k < 4 && v >= C.edges[k + 1]) k++; return k; }
function renderCrowd() {
  const C = CROWD[state.coin]; crowdBox.hidden = !(C && C.edges); if (crowdBox.hidden) return;
  const coin = state.coin.replace("USDT", ""), m = C.m5;
  let now = null, nowT = null;
  if (m) for (let i = m.acc.length - 1; i >= 0; i--) if (m.acc[i] != null) { now = m.acc[i]; nowT = m.t0 + i * m.step; break; }
  if (now == null) { now = C.latest_lsr; nowT = null; }
  const k = fifthOf(C, now), pct = v => Math.round(v / (1 + v) * 100), e = C.edges;
  const names = ["Fewest accounts long", "Fewer long", "Middle", "More long", "Most accounts long"];
  document.getElementById("crowdnow").innerHTML = `${coin} now: <b>${now.toFixed(2)}</b> long accounts per short account (${pct(now)}% of accounts long)` +
    (nowT ? ` at ${fmtT(nowT + WIB)} WIB` : "") + ` → <b>${names[k].toLowerCase()}</b> group (${k + 1} of 5).`;
  const cell = x => x.median == null ? "<td>–</td><td>–</td>" : `<td class="strong ${x.median >= 0 ? "pp" : "pn"}">${x.median >= 0 ? "+" : "−"}${Math.abs(x.median).toFixed(1)}%</td><td>${x.up.toFixed(0)}%</td>`;
  document.getElementById("crowdbody").innerHTML = C.all.rows.map((row, j) => {
    const lo = j === 0 ? null : e[j], hi = j === 4 ? null : e[j + 1];
    const rng = lo == null ? `below ${hi.toFixed(2)}` : hi == null ? `${lo.toFixed(2)} or more` : `${lo.toFixed(2)}–${hi.toFixed(2)}`;
    const sh = lo == null ? `under ${pct(hi)}%` : hi == null ? `${pct(lo)}% or more` : `${pct(lo)}–${pct(hi)}%`;
    return `<tr${j === k ? ' class="now"' : ""}><th scope="row">${names[j]}${j === k ? ' <span class="tag">now</span>' : ""}<small>ratio ${rng} · ${sh} of accounts long</small></th>${cell(row)}<td>${row.days}</td>${cell(C.recent.rows[j])}</tr>`;
  }).join("") + `<tr class="sum"><th scope="row">All days (baseline)</th><td class="strong">${C.all.base_median >= 0 ? "+" : "−"}${Math.abs(C.all.base_median).toFixed(1)}%</td><td>${C.all.base_up.toFixed(0)}%</td><td>${C.all.days}</td><td class="strong">${C.recent.base_median >= 0 ? "+" : "−"}${Math.abs(C.recent.base_median).toFixed(1)}%</td><td>${C.recent.base_up.toFixed(0)}%</td></tr>`;
  document.getElementById("crowdhdr1").textContent = `${C.from.slice(0, 4)}–now`;
  document.getElementById("crowdhdr2").textContent = `${C.recent_from.slice(0, 4)}–now`;
}
for (const k of COINS) document.getElementById("coin-" + k).addEventListener("click", renderCrowd);
Promise.all(COINS.map(c => fetch(`hist/${c}_crowd.json`, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(j => { if (j) CROWD[c] = j; }).catch(() => {})))
  .then(() => { renderCrowd(); if (bars.length) setData(true); });

// ---------- CME institutions: CFTC weekly report (data/cftc/cme_tff.csv, collected by collector/cftc.py) ----------
// Positions in coins, all CME contracts of the coin added together (big + micro). Net = long - short; spread positions
// (a long and a short held together by the same trader) are left out because they do not change the net position.
const COT = DATA.cftc || {};
const COT_ROWS = [ // key, name, who, colour token (null = table only)
  ["lev", "Hedge funds", "“leveraged funds”", "--c1"],
  ["am", "Asset managers", "pension funds, insurers, mutual funds", "--c2"],
  ["dealer", "Dealers", "banks and market makers", "--c3"],
  ["nr", "Small traders", "below the reporting threshold", "--c4"],
  ["oth", "Other large traders", "", null],
];
const fmtD = t => new Date(t * 1000).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const sq = v => (v < 0 ? "−" : v > 0 ? "+" : "") + qty(v);
const cotBox = document.getElementById("cot");
const cotChart = LC.createChart(document.getElementById("cotchart"), {
  autoSize: true,
  layout: { background: { type: "solid", color: css("--panel") }, textColor: css("--muted"), fontFamily: css("--font-ui"), fontSize: 11 },
  grid: { vertLines: { color: "rgba(255,255,255,0.035)" }, horzLines: { color: "rgba(255,255,255,0.035)" } },
  crosshair: { mode: LC.CrosshairMode.Magnet, vertLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" }, horzLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" } },
  rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: false, rightOffset: 2 },
  localization: { timeFormatter: t => "Tue " + fmtD(t) },
});
const cotSeries = {};
for (const [k, , , tok] of COT_ROWS) if (tok)
  cotSeries[k] = cotChart.addSeries(LC.LineSeries, { color: css(tok), lineWidth: 2, lastValueVisible: false, priceLineVisible: false, crosshairMarkerRadius: 4, priceFormat: { type: "custom", formatter: sq, minMove: 0.1 } });
cotSeries.lev.createPriceLine({ price: 0, color: "#3a4150", lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
let cotRange = 3 * 365;
function binanceOi(coin) { const o = DATA[coin].c5.oi; for (let i = o.length - 1; i >= 0; i--) if (o[i] != null) return o[i]; return null; }
function cotTable(i) {
  const D = COT[state.coin]; if (!D) return;
  const n = D.t.length; if (i == null || i < 0 || i >= n) i = n - 1;
  const coin = state.coin.replace("USDT", ""), p = i > 0 ? i - 1 : null;
  const net = (k, j) => D[k + "_l"][j] - D[k + "_s"][j];
  document.getElementById("cotweek").textContent = `Positions on Tue ${fmtD(D.t[i])}` + (i === n - 1 ? " (latest report)" : "") + ` · in ${coin}`;
  document.getElementById("cotbody").innerHTML = COT_ROWS.map(([k, name, who, tok]) => {
    const ch = p == null ? null : net(k, i) - net(k, p);
    return `<tr><th scope="row">${tok ? `<span class="sw" style="background:var(${tok})"></span>` : `<span class="sw blank"></span>`}${name}${who ? `<small>${who}</small>` : ""}</th>` +
      `<td>${qty(D[k + "_l"][i])}</td><td>${qty(D[k + "_s"][i])}</td><td class="strong">${sq(net(k, i))}</td><td>${ch == null ? "–" : sq(ch)}</td></tr>`;
  }).join("");
  const bo = binanceOi(state.coin);
  document.getElementById("cotfoot").textContent = `CME open interest that week: ${qty(D.oi[i])} ${coin}` +
    (bo != null ? ` · Binance ${state.coin} perpetual now: ${qty(bo)} ${coin}` : "");
}
function cotApplyRange() {
  const D = COT[state.coin]; if (!D) return;
  const n = D.t.length, last = D.t[n - 1];
  let from = 0; if (cotRange) while (from < n - 1 && D.t[from] < last - cotRange * 86400) from++;
  // logical range (bar indexes) also works before the chart has its final size (first draw, coin switch)
  requestAnimationFrame(() => cotChart.timeScale().setVisibleLogicalRange({ from: from - 0.5, to: n - 1 + 2 }));
  for (const b of document.querySelectorAll("#cotranges .btn")) b.setAttribute("aria-pressed", +b.dataset.d === cotRange);
}
function setCot() {
  const D = COT[state.coin];
  cotBox.hidden = !D; if (!D) return;
  for (const k in cotSeries) cotSeries[k].setData(D.t.map((t, j) => ({ time: t, value: D[k + "_l"][j] - D[k + "_s"][j] })));
  const last = D.t[D.t.length - 1];
  document.getElementById("cotasof").textContent = `Latest report: positions on Tue ${fmtD(last)} · CFTC publishes each Friday, so this updates once a week`;
  cotApplyRange(); cotTable();
}
for (const b of document.querySelectorAll("#cotranges .btn")) b.onclick = () => { cotRange = +b.dataset.d; cotApplyRange(); };
cotChart.subscribeCrosshairMove(p => {
  const D = COT[state.coin]; if (!D) return;
  cotTable(p && p.time != null ? D.t.indexOf(p.time) : null);
});
for (const k of COINS) document.getElementById("coin-" + k).addEventListener("click", setCot);

// ---------- Stablecoin supply (data/stablecoins/daily.csv from DefiLlama, collected by collector/stablecoins.py) ----------
// Same for every coin: total of all US-dollar stablecoins, USDT and USDC, in billions of US$, plus the 30-day change of the total.
const ST = DATA.stable;
const stableBox = document.getElementById("stable");
const fmtB = v => v == null ? "–" : "$" + v.toFixed(Math.abs(v) >= 100 ? 1 : 2) + "B";
const fmtBd = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + "$" + Math.abs(v).toFixed(Math.abs(v) >= 100 ? 0 : 1) + "B";
const stableChart = LC.createChart(document.getElementById("stablechart"), {
  autoSize: true,
  layout: { background: { type: "solid", color: css("--panel") }, textColor: css("--muted"), fontFamily: css("--font-ui"), fontSize: 11, panes: { separatorColor: css("--line") } },
  grid: { vertLines: { color: "rgba(255,255,255,0.035)" }, horzLines: { color: "rgba(255,255,255,0.035)" } },
  crosshair: { mode: LC.CrosshairMode.Magnet, vertLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" }, horzLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" } },
  rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: false, rightOffset: 2 },
  localization: { timeFormatter: t => fmtD(t) },
});
const stLine = (tok, w) => stableChart.addSeries(LC.LineSeries, { color: css(tok), lineWidth: w, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3, priceFormat: { type: "custom", formatter: fmtB, minMove: 0.01 } }, 0);
const stTot = stLine("--fg", 2), stUsdt = stLine("--c2", 1.5), stUsdc = stLine("--c4", 1.5);
const stChg = stableChart.addSeries(LC.HistogramSeries, { priceFormat: { type: "custom", formatter: fmtBd, minMove: 0.01 }, lastValueVisible: true, priceLineVisible: false, base: 0 }, 1);
{ const p = stableChart.panes(); if (p[0]) p[0].setStretchFactor(2.2); if (p[1]) p[1].setStretchFactor(1); }
let stableRange = 365;
const stBack = (arr, i, days) => { // value `days` calendar days before index i (daily rows, may have gaps)
  if (!ST || arr[i] == null) return null;
  const want = ST.t[i] - days * 86400; let j = i;
  while (j > 0 && ST.t[j] > want) j--;
  return ST.t[j] <= want && arr[j] != null ? arr[i] - arr[j] : null;
};
const stPct = (arr, i, days) => { const d = stBack(arr, i, days); const base = d == null ? null : arr[i] - d; return d == null || !base ? null : 100 * d / base; };
function stableTable(i) {
  if (!ST) return;
  const n = ST.t.length; if (i == null || i < 0 || i >= n) i = n - 1;
  document.getElementById("stableweek").textContent = `Supply on ${fmtD(ST.t[i])}` + (i === n - 1 ? " (latest, today so far)" : "") + " · US$";
  const cell = (arr, d) => { const v = stBack(arr, i, d), p = stPct(arr, i, d); return `<td class="${v > 0 ? "pp" : v < 0 ? "pn" : ""}">${fmtBd(v)}${p == null ? "" : `<br><small>${p > 0 ? "+" : p < 0 ? "−" : ""}${Math.abs(p).toFixed(1)}%</small>`}</td>`; };
  const row = (name, tok, arr) => `<tr><th scope="row"><span class="sw" style="background:var(${tok})"></span>${name}</th><td class="strong">${fmtB(arr[i])}</td>${cell(arr, 7)}${cell(arr, 30)}${cell(arr, 365)}</tr>`;
  document.getElementById("stablebody").innerHTML = row("All dollar stablecoins", "--fg", ST.total) + row("USDT (Tether)", "--c2", ST.usdt) + row("USDC (Circle)", "--c4", ST.usdc);
  let pk = 0; for (let j = 0; j <= i; j++) if (ST.total[j] != null && ST.total[j] > (ST.total[pk] ?? -1)) pk = j;
  document.getElementById("stablefoot").textContent = `Highest total up to this day: ${fmtB(ST.total[pk])} on ${fmtD(ST.t[pk])}` + (pk === i ? " (this day)" : `, this day ${(100 * (1 - ST.total[i] / ST.total[pk])).toFixed(1)}% below it`);
}
function stableApplyRange() {
  if (!ST) return;
  const n = ST.t.length, last = ST.t[n - 1];
  let from = 0; if (stableRange) while (from < n - 1 && ST.t[from] < last - stableRange * 86400) from++;
  requestAnimationFrame(() => stableChart.timeScale().setVisibleLogicalRange({ from: from - 0.5, to: n - 1 + 2 }));
  for (const b of document.querySelectorAll("#stableranges .btn")) b.setAttribute("aria-pressed", +b.dataset.d === stableRange);
}
function setStable() {
  stableBox.hidden = !(ST && ST.t && ST.t.length); if (stableBox.hidden) return;
  const ln = arr => ST.t.map((t, j) => arr[j] != null ? { time: t, value: arr[j] } : { time: t });
  stTot.setData(ln(ST.total)); stUsdt.setData(ln(ST.usdt)); stUsdc.setData(ln(ST.usdc));
  const pos = css("--c1"), neg = css("--c3");
  stChg.setData(ST.t.map((t, j) => { const v = stBack(ST.total, j, 30); return v == null ? { time: t } : { time: t, value: v, color: v >= 0 ? pos : neg }; }));
  document.getElementById("stableasof").textContent = `Daily (UTC) · latest: ${fmtD(ST.t[ST.t.length - 1])} · same for BTC and ETH`;
  stableApplyRange(); stableTable();
}
for (const b of document.querySelectorAll("#stableranges .btn")) b.onclick = () => { stableRange = +b.dataset.d; stableApplyRange(); };
stableChart.subscribeCrosshairMove(p => { if (!ST) return; stableTable(p && p.time != null ? ST.t.indexOf(p.time) : null); });

const B5 = DATA.BTCUSDT, last5 = Math.max(B5.c5.t[B5.c5.t.length - 1] + 300, B5.c1.t[B5.c1.t.length - 1] + 60);
document.getElementById("asof").textContent = "Data to " + fmtT(last5 + WIB) + " WIB · built " + fmtT(DATA.built + WIB) + " WIB";
document.getElementById("days").textContent = Math.round((B5.c5.t[B5.c5.t.length - 1] - B5.c5.t[0]) / 86400);
document.getElementById("cover").textContent = `Coverage: 1D/1W/1M from the Binance public archive (candles since Jan 2020, open interest since Sep 2020) joined with this repo; 5m-4h: the last ${Math.round((B5.c5.t[B5.c5.t.length - 1] - B5.c5.t[0]) / 86400)} days of 5-minute data; 1m: from ${fmtT(DATA.BTCUSDT.c1.t[0] + WIB)}; actual liquidations from ${fmtT(DATA.BTCUSDT.l5.first + WIB)}.`;
if (!DATA[state.coin]) state.coin = "BTCUSDT";
if (!TFS.some(x => x[1] === state.tf)) state.tf = 900;
pressed();
// ---------- Hyperliquid positions (data/hyperliquid from collector/hyperliquid.py) ----------
// Real long and short positions of tracked Hyperliquid accounts, by entry price or liquidation price. Hyperliquid only.
const HL = DATA.hl || {};
const hlBox = document.getElementById("hl");
let hlMode = "entry";
const hlChart = LC.createChart(document.getElementById("hlchart"), {
  autoSize: true,
  layout: { background: { type: "solid", color: css("--panel") }, textColor: css("--muted"), fontFamily: css("--font-ui"), fontSize: 11 },
  grid: { vertLines: { color: "rgba(255,255,255,0.035)" }, horzLines: { color: "rgba(255,255,255,0.035)" } },
  crosshair: { mode: LC.CrosshairMode.Magnet, vertLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" }, horzLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" } },
  rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: true, rightOffset: 2 },
  localization: { timeFormatter: t => fmtT(t + WIB) + " WIB" },
});
const hlPct = { type: "custom", formatter: v => v.toFixed(0) + "%", minMove: 0.1 };
const hlAll = hlChart.addSeries(LC.LineSeries, { color: css("--fg"), lineWidth: 2, priceLineVisible: false, priceFormat: hlPct });
const hlBig = hlChart.addSeries(LC.LineSeries, { color: css("--c2"), lineWidth: 1.5, priceLineVisible: false, priceFormat: hlPct });
const hlSmall = hlChart.addSeries(LC.LineSeries, { color: css("--c4"), lineWidth: 1.5, priceLineVisible: false, priceFormat: hlPct, lineStyle: 0, pointMarkersVisible: true });
hlAll.createPriceLine({ price: 50, color: "#3a4150", lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
const svgEl = (tag, attrs, text) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; };
function hlProfile(H) {
  const P = H.prof, coin = state.coin.replace("USDT", ""), step = P.step, mark = P.mark;
  const L = hlMode === "entry" ? P.entryL : P.liqL, S = hlMode === "entry" ? P.entryS : P.liqS;
  const span = hlMode === "entry" ? 0.3 : 0.4;                      // rows within +-30% (entry) or +-40% (liquidation) of price
  const v = (o, k) => +(o[String(k)] || 0);
  let lo = Math.floor(mark * (1 - span) / step) * step, hi = Math.floor(mark * (1 + span) / step) * step;
  const has = Object.keys(L).concat(Object.keys(S)).map(Number).filter(k => k >= lo && k <= hi && (v(L, k) > 0 || v(S, k) > 0));
  if (has.length) {                                                 // trim empty rows, keep a little room around the price
    const m0 = Math.floor(mark / step) * step;
    lo = Math.min(Math.min(...has), m0 - 2 * step); hi = Math.max(Math.max(...has), m0 + 2 * step);
  }
  const rows = []; for (let k = hi; k >= lo; k -= step) rows.push(k);
  let mx = 0; for (const k of rows) mx = Math.max(mx, v(L, k), v(S, k));
  const box = document.getElementById("hlprof"); box.innerHTML = "";
  if (!mx) { box.textContent = "No tracked positions in this range yet."; return; }
  const rh = 13, W = Math.max(300, Math.min(700, (box.clientWidth || 600) - 8)), lab = 66, cx = lab + (W - lab) / 2, half = (W - lab) / 2 - 4, H2 = rows.length * rh + 22;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H2}`, role: "img", "aria-label": `${coin} long and short positions by ${hlMode === "entry" ? "entry" : "liquidation"} price` });
  const cL = css("--c1"), cS = css("--c3"), dec = step < 1 ? 2 : 0;
  svg.appendChild(svgEl("text", { x: cx + 6, y: 11 }, "Longs →"));
  svg.appendChild(svgEl("text", { x: cx - 6, y: 11, "text-anchor": "end" }, "← Shorts"));
  rows.forEach((k, j) => {
    const y = 18 + j * rh, l = v(L, k), s = v(S, k);
    if (j % Math.max(1, Math.round(rows.length / 18)) === 0) svg.appendChild(svgEl("text", { x: lab - 6, y: y + rh - 3, "text-anchor": "end" }, "$" + k.toLocaleString("en-US", { maximumFractionDigits: dec })));
    const tip = (side, q) => `${side} ${hlMode === "entry" ? "entered" : "liquidated"} at $${k.toLocaleString("en-US")}–${(k + step).toLocaleString("en-US")}: ${qty(q)} ${coin} ($${(q * mark / 1e6).toFixed(1)}M at today's price)`;
    if (l > 0) { const r = svgEl("rect", { x: cx, y: y + 1, width: Math.max(1, half * l / mx), height: rh - 2, fill: cL, rx: 1 }); r.appendChild(svgEl("title", {}, tip("Longs", l))); svg.appendChild(r); }
    if (s > 0) { const w = Math.max(1, half * s / mx); const r = svgEl("rect", { x: cx - w, y: y + 1, width: w, height: rh - 2, fill: cS, rx: 1 }); r.appendChild(svgEl("title", {}, tip("Shorts", s))); svg.appendChild(r); }
  });
  svg.appendChild(svgEl("line", { x1: cx, x2: cx, y1: 16, y2: H2 - 2, stroke: css("--line") }));
  const ym = 18 + (hi - mark) / step * rh + rh / 2;
  svg.appendChild(svgEl("line", { x1: lab, x2: W, y1: ym, y2: ym, stroke: css("--fg"), "stroke-dasharray": "4 3", "stroke-width": 1 }));
  svg.appendChild(svgEl("text", { x: W - 2, y: ym - 3, "text-anchor": "end", style: "fill:var(--fg)" }, `now $${mark.toLocaleString("en-US", { maximumFractionDigits: dec })}`));
  box.appendChild(svg);
}
function hlTable(H) {
  const s = H.last, coin = state.coin.replace("USDT", ""), mark = s.mark, n = H.t.length;
  const usd = q => "$" + (q * mark / 1e6).toFixed(0) + "M";
  const pctv = x => x == null ? "–" : (100 * x).toFixed(0) + "%";
  const money = x => x == null ? "–" : "$" + x.toLocaleString("en-US", { maximumFractionDigits: x < 100 ? 2 : 0 });
  const bigShare = s.big_szL + s.big_szS > 0 ? 100 * s.big_szL / (s.big_szL + s.big_szS) : null;
  const sm = H.sm.length ? H.sm[H.sm.length - 1] : null;
  document.getElementById("hlwk").textContent = `Tracked accounts on ${fmtT(s.t + WIB)} WIB · ${coin}`;
  const row = (name, a, b, cls = "") => `<tr><th scope="row">${name}</th><td class="${cls}">${a}</td><td class="${cls}">${b}</td></tr>`;
  document.getElementById("hlbody").innerHTML =
    row("Accounts", s.nL.toLocaleString("en-US"), s.nS.toLocaleString("en-US")) +
    row(`Position size<small>${coin} (US$ at today's price)</small>`, `${qty(s.szL)} (${usd(s.szL)})`, `${qty(s.szS)} (${usd(s.szS)})`, "strong") +
    row("Average entry price", money(s.avgL), money(s.avgS)) +
    row("Share of size in loss", pctv(s.lossL), pctv(s.lossS)) +
    row(`Accounts worth $1M or more<small>share of their size</small>`, bigShare == null ? "–" : bigShare.toFixed(0) + "%", bigShare == null ? "–" : (100 - bigShare).toFixed(0) + "%") +
    (sm == null ? "" : row(`Smaller accounts, random sample<small>share of positions, ${fmtD(H.smt[H.smt.length - 1])} (${H.smn[H.smn.length - 1]} positions)</small>`, sm.toFixed(0) + "%", (100 - sm).toFixed(0) + "%"));
  document.getElementById("hlfoot").textContent = `Tracked: about ${H.cover[n - 1] == null ? "–" : H.cover[n - 1].toFixed(0) + "%"} of Hyperliquid's ${qty(s.oi)} ${coin} open contracts · ${s.queried.toLocaleString("en-US")} accounts checked this hour`;
}
function setHl() {
  const H = HL[state.coin];
  hlBox.hidden = !H; if (!H) return;
  const ln = (t, a) => t.map((x, j) => a[j] != null ? { time: x, value: a[j] } : { time: x });
  hlAll.setData(ln(H.t, H.ls)); hlBig.setData(ln(H.t, H.big)); hlSmall.setData(ln(H.smt, H.sm));
  requestAnimationFrame(() => hlChart.timeScale().fitContent());
  document.getElementById("hlasof").textContent = `Hourly · started 14 Nov 2026 · ${H.t.length} snapshot${H.t.length === 1 ? "" : "s"} so far`;
  for (const b of document.querySelectorAll("#hlmode .btn")) b.setAttribute("aria-pressed", b.dataset.m === hlMode);
  hlProfile(H); hlTable(H);
}
for (const b of document.querySelectorAll("#hlmode .btn")) b.onclick = () => { hlMode = b.dataset.m; setHl(); };
{ let hlRs = null; window.addEventListener("resize", () => { clearTimeout(hlRs); hlRs = setTimeout(() => { const H = HL[state.coin]; if (H && !hlBox.hidden) hlProfile(H); }, 200); }); }
for (const k of COINS) document.getElementById("coin-" + k).addEventListener("click", setHl);

setEtf();
setStable();
setHl();
setCot();
refresh(false, () => applyRange(HIST[state.tf] ? 365 : 3));
new ResizeObserver(() => requestAnimationFrame(placeLabels)).observe(document.getElementById("chart"));
})();
