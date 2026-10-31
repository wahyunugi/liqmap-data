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
const CROWD = {};   // coin -> hist/<coin>_crowd.json (account long/short ratios + 30-day statistics), loaded at start
function addPrem(coin, out, tf) { // per bar: Coinbase premium and Binance long/short ratios, averaged over the bar
  const P = DATA[coin].prem || {}, src = HIST[tf] ? P.d1 : P.m5, C = CROWD[coin] && CROWD[coin].m5;
  const A = C && { t0: C.t0, step: C.step, p: C.acc }, T = C && { t0: C.t0, step: C.step, p: C.top };
  out.forEach((r, i) => { const end = i + 1 < out.length ? out[i + 1].b : r.b + (HIST[tf] ? Math.max(tf, 86400) : tf);
    const a = tf === 60 ? Math.floor(r.b / 300) * 300 : r.b, b = tf === 60 ? a + 300 : end;
    r.prem = premAvg(src, a, b);
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
const fmtUsd = { type: "custom", formatter: v => usd(v), minMove: 1 };
const liqS = chart.addSeries(LC.HistogramSeries, { color: css("--short"), priceFormat: fmtUsd, lastValueVisible: false, priceLineVisible: false, base: 0 }, 1);
const liqL = chart.addSeries(LC.HistogramSeries, { color: css("--long"), priceFormat: fmtUsd, lastValueVisible: false, priceLineVisible: false, base: 0 }, 1);
const oiS = chart.addSeries(LC.LineSeries, { color: css("--oi"), lineWidth: 2, priceFormat: { type: "custom", formatter: qty, minMove: 0.001 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 2);
const volS = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "custom", formatter: qty, minMove: 0.001 }, lastValueVisible: false, priceLineVisible: false }, 3);
const fmtPrem = v => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(3) + "%";
const premS = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "custom", formatter: fmtPrem, minMove: 0.0001 }, lastValueVisible: false, priceLineVisible: false, base: 0 }, 4);
const fmtR = v => v.toFixed(2);
const lsrA = chart.addSeries(LC.LineSeries, { color: css("--c4"), lineWidth: 2, priceFormat: { type: "custom", formatter: fmtR, minMove: 0.001 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 5);
const lsrT = chart.addSeries(LC.LineSeries, { color: css("--c2"), lineWidth: 2, priceFormat: { type: "custom", formatter: fmtR, minMove: 0.001 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 5);
lsrA.createPriceLine({ price: 1, color: "#3a4150", lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
const panes = chart.panes();
[5, 1.4, 1.1, 0.9, 1, 1].forEach((f, i) => panes[i] && panes[i].setStretchFactor(f));

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
  lp.innerHTML = `<b>Actual liquidations</b>` + (r.hasLiq ? `<span class="sh">shorts ${usd(r.liqS)}</span> · <span class="lg">longs ${usd(r.liqL)}</span>` : `no data before ${fmtT(DATA[c][state.tf === 60 ? "l1" : "l5"].first + WIB)}`);
  op.innerHTML = `<b>Open interest</b>${r.oi != null ? qty(r.oi) + " " + c.replace("USDT", "") + " ≈ " + usd(r.oi * r.c) : "–"}`;
  vp.innerHTML = `<b>Volume</b>${qty(r.v)} ${c.replace("USDT", "")}`;
  const share = v => Math.round(v / (1 + v) * 100);
  document.getElementById("pl5").innerHTML = `<b>Long vs short</b>` + (r.lsr != null || r.tpr != null ?
    (r.lsr != null ? `<span class="ca">all accounts ${r.lsr.toFixed(2)}</span> <span class="k">(${share(r.lsr)}% of accounts long)</span>` : "") +
    (r.tpr != null ? ` · <span class="cb">big accounts ${r.tpr.toFixed(2)}</span> <span class="k">(by position size)</span>` : "") : "no data for this candle");
  const pr = document.getElementById("pl4"), P = DATA[c].prem;
  pr.innerHTML = `<b>Coinbase premium</b>` + (r.prem != null ? `<span class="${r.prem >= 0 ? "pp" : "pn"}">${fmtPrem(r.prem)}</span> <span class="k">${r.prem >= 0 ? "Coinbase pricier: US buyers more eager" : "Coinbase cheaper: US sellers more eager"}</span>`
    : (() => { const S = P && P[HIST[state.tf] ? "d1" : "m5"]; return !S ? "no data" : r.b < S.t0 ? "no data before " + fmtT(S.t0 + WIB) : "not available for this candle yet"; })());
}
function placeLabels() {
  let y = 0; const ids = ["pl1", "pl2", "pl3", "pl4", "pl5"];
  for (let p = 0; p < 6; p++) { const h = chart.paneSize(p).height; if (p > 0) document.getElementById(ids[p - 1]).style.top = (y + 5) + "px"; y += h + 1; }
}
chart.subscribeCrosshairMove(p => {
  const i = (p && p.logical != null && p.point) ? Math.round(p.logical) : null;
  state.hover = (i != null && i >= 0 && i < bars.length) ? i : null;
  state.hoverPrice = (state.hover != null && p.paneIndex === 0 && p.point) ? candles.coordinateToPrice(p.point.y) : null;
  renderLegend(); if (state.map) heat.update();
});

// ---------- data loading / controls ----------
function setData(keepRange) {
  const prev = keepRange ? chart.timeScale().getVisibleRange() : null;
  bars = buildBars(state.coin, state.tf);
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

const B5 = DATA.BTCUSDT, last5 = Math.max(B5.c5.t[B5.c5.t.length - 1] + 300, B5.c1.t[B5.c1.t.length - 1] + 60);
document.getElementById("asof").textContent = "Data to " + fmtT(last5 + WIB) + " WIB · built " + fmtT(DATA.built + WIB) + " WIB";
document.getElementById("days").textContent = Math.round((B5.c5.t[B5.c5.t.length - 1] - B5.c5.t[0]) / 86400);
document.getElementById("cover").textContent = `Coverage: 1D/1W/1M from the Binance public archive (candles since Jan 2020, open interest since Sep 2020) joined with this repo; 5m-4h: the last ${Math.round((B5.c5.t[B5.c5.t.length - 1] - B5.c5.t[0]) / 86400)} days of 5-minute data; 1m: from ${fmtT(DATA.BTCUSDT.c1.t[0] + WIB)}; actual liquidations from ${fmtT(DATA.BTCUSDT.l5.first + WIB)}.`;
if (!DATA[state.coin]) state.coin = "BTCUSDT";
if (!TFS.some(x => x[1] === state.tf)) state.tf = 900;
pressed();
setEtf();
setCot();
refresh(false, () => applyRange(HIST[state.tf] ? 365 : 3));
new ResizeObserver(() => requestAnimationFrame(placeLabels)).observe(document.getElementById("chart"));
})();
