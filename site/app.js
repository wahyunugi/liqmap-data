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
const TFS = [["1m",60],["5m",300],["15m",900],["1h",3600],["4h",14400],["1D",86400]];
const RANGES = [["1D",1],["3D",3],["1W",7],["2W",14],["All",0]];
// Heatmap window in 5-minute candles. 24h = model v6 as checked against CoinGlass; 3D/7D = same rules, levels kept longer.
const WINS = [["Auto",0],["24h",288],["3D",864],["7D",2016]];
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

const state = { coin: "BTCUSDT", tf: 900, win: 0, heat: true, map: true, thr: 0.6, hover: null, hoverPrice: null };
try { const s = JSON.parse(localStorage.getItem("liqmap-ui") || "{}"); Object.assign(state, s); } catch (e) {}
const COINS = ["BTCUSDT", "ETHUSDT"];
const stores = {};
let bars = [], store = null;

// ---------- data per interval ----------
function effWin(tf) { // long windows only from 1h candles up: on short candles they add little and cost time
  if (tf < 3600) return 288;
  if (state.win) return state.win;
  return tf >= 86400 ? 2016 : tf >= 14400 ? 864 : 288;
}
function storeKey(coin, tf) { const w = effWin(tf); return w === 288 ? coin + "|288" : coin + "|" + w + "|" + tf; }
function getStore(coin, tf, snaps) {
  const key = storeKey(coin, tf);
  if (!stores[key]) {
    const c = DATA[coin].c5, w = effWin(tf);
    let want = null;
    if (w !== 288) { want = new Uint8Array(c.t.length); for (const j of snaps) if (j >= 0 && j < want.length) want[j] = 1; }
    stores[key] = LiqModel.build(c, LiqModel.binsFor(c.c[c.c.length - 1]), w, want);
  }
  return stores[key];
}
function buildBars(coin, tf) {
  const D = DATA[coin], c5 = D.c5, src = tf === 60 ? D.c1 : c5, L = tf === 60 ? D.l1 : D.l5;
  const out = [], liq = new Map();
  for (let i = 0; i < L.t.length; i++) { const b = Math.floor(L.t[i] / tf) * tf; const a = liq.get(b) || [0, 0]; a[0] += L.l[i]; a[1] += L.s[i]; liq.set(b, a); }
  const liqFrom = L.first == null ? Infinity : Math.floor(L.first / tf) * tf;
  let cur = null;
  for (let i = 0; i < src.t.length; i++) {
    const t = src.t[i], b = Math.floor(t / tf) * tf;
    if (!cur || cur.b !== b) { cur = { b, o: src.o[i], h: src.h[i], l: src.l[i], c: src.c[i], v: 0, oi: null, snap: -1 }; out.push(cur); }
    cur.h = Math.max(cur.h, src.h[i]); cur.l = Math.min(cur.l, src.l[i]); cur.c = src.c[i]; cur.v += src.v[i] || 0;
    if (src.oi[i] != null) cur.oi = src.oi[i];
    // heatmap column = state at the close of the latest 5-minute candle that has closed by this bar's close
    const j = tf === 60 ? Math.floor((t + 60 - 300 - c5.t[0]) / 300) : i;
    cur.snap = j;
  }
  store = getStore(coin, tf, out.map(r => r.snap));
  for (const r of out) if (!(r.snap >= store.first && r.snap < store.n)) r.snap = -1;
  for (const r of out) { const a = liq.get(r.b); r.liqL = a ? a[0] : 0; r.liqS = a ? a[1] : 0; r.hasLiq = r.b >= liqFrom; r.time = r.b + WIB; }
  return out;
}

// ---------- chart ----------
const LC = LightweightCharts;
const chart = LC.createChart(document.getElementById("chart"), {
  autoSize: true,
  layout: { background: { type: "solid", color: css("--panel") }, textColor: css("--muted"), fontFamily: css("--font-ui"), fontSize: 11, panes: { separatorColor: css("--line"), separatorHoverColor: "#2b3240" } },
  grid: { vertLines: { color: "rgba(255,255,255,0.035)" }, horzLines: { color: "rgba(255,255,255,0.035)" } },
  crosshair: { mode: LC.CrosshairMode.Normal, vertLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" }, horzLine: { color: "#6b7385", labelBackgroundColor: "#2b3240" } },
  rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: true, secondsVisible: false, rightOffset: 6 },
  localization: { timeFormatter: t => fmtT(t) + " WIB" },
});
const candles = chart.addSeries(LC.CandlestickSeries, { upColor: css("--up"), downColor: css("--down"), borderUpColor: css("--up"), borderDownColor: css("--down"), wickUpColor: css("--up"), wickDownColor: css("--down"), priceLineColor: "#9aa3b5", priceLineStyle: 2 }, 0);
const fmtUsd = { type: "custom", formatter: v => usd(v), minMove: 1 };
const liqS = chart.addSeries(LC.HistogramSeries, { color: css("--short"), priceFormat: fmtUsd, lastValueVisible: false, priceLineVisible: false, base: 0 }, 1);
const liqL = chart.addSeries(LC.HistogramSeries, { color: css("--long"), priceFormat: fmtUsd, lastValueVisible: false, priceLineVisible: false, base: 0 }, 1);
const oiS = chart.addSeries(LC.LineSeries, { color: css("--oi"), lineWidth: 2, priceFormat: { type: "custom", formatter: qty, minMove: 0.001 }, lastValueVisible: true, priceLineVisible: false, crosshairMarkerRadius: 3 }, 2);
const volS = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "custom", formatter: qty, minMove: 0.001 }, lastValueVisible: false, priceLineVisible: false }, 3);
const panes = chart.panes();
[5, 1.4, 1.1, 0.9].forEach((f, i) => panes[i] && panes[i].setStretchFactor(f));

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
    ctx.fillText((state.hover != null ? "Map at " + fmtT(bars[i].time) : "Map now") + " · max " + usd(mx), Math.round(right * hr), Math.round((Hm - 6) * vrt));
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
  lp.innerHTML = `<b>Actual liquidations</b>` + (r.hasLiq ? `<span class="sh">shorts ${usd(r.liqS)}</span> · <span class="lg">longs ${usd(r.liqL)}</span>` : `no data before ${fmtT(Math.floor(DATA[c][state.tf === 60 ? "l1" : "l5"].first / state.tf) * state.tf + WIB)}`);
  op.innerHTML = `<b>Open interest</b>${r.oi != null ? qty(r.oi) + " " + c.replace("USDT", "") + " ≈ " + usd(r.oi * r.c) : "–"}`;
  vp.innerHTML = `<b>Volume</b>${qty(r.v)} ${c.replace("USDT", "")}`;
}
function placeLabels() {
  let y = 0; const ids = ["pl1", "pl2", "pl3"];
  for (let p = 0; p < 4; p++) { const h = chart.paneSize(p).height; if (p > 0) document.getElementById(ids[p - 1]).style.top = (y + 5) + "px"; y += h + 1; }
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
function save() { try { localStorage.setItem("liqmap-ui", JSON.stringify({ coin: state.coin, tf: state.tf, win: state.win, heat: state.heat, map: state.map, thr: state.thr })); } catch (e) {} }
function pressed() {
  for (const k of COINS) document.getElementById("coin-" + k).setAttribute("aria-pressed", k === state.coin);
  for (const [n, s] of TFS) document.getElementById("tf-" + n).setAttribute("aria-pressed", s === state.tf);
  const w = effWin(state.tf), short = state.tf < 3600;
  for (const [n, v] of WINS) { const b = document.getElementById("win-" + n);
    b.setAttribute("aria-pressed", v === 0 ? (state.win === 0 && !short) : (!short && state.win !== 0 && v === state.win) || (short && v === 288));
    b.disabled = short && v !== 288;
    b.title = short && v !== 288 ? "Longer windows are available from the 1h interval up" : ""; }
  document.getElementById("winnow").textContent = (state.win === 0 && !short) ? "= " + WINS.find(x => x[1] === w)[0] : "";
}
const winBox = document.getElementById("wins");
for (const [n, v] of WINS) { const b = document.createElement("button"); b.className = "btn"; b.id = "win-" + n; b.textContent = n;
  b.onclick = () => { state.win = v; save(); pressed(); withLoading(() => setData(true)); }; winBox.appendChild(b); }
{ const sp = document.createElement("span"); sp.id = "winnow"; sp.className = "winnow"; winBox.appendChild(sp); }
const tfBox = document.getElementById("tfs"), rgBox = document.getElementById("ranges");
for (const [n, s] of TFS) { const b = document.createElement("button"); b.className = "btn"; b.id = "tf-" + n; b.textContent = n;
  if (s === 60) b.title = "1-minute data covers only the last ~27 hours";
  b.onclick = () => { state.tf = s; save(); pressed(); withLoading(() => setData(true)); }; tfBox.appendChild(b); }
for (const [n, d] of RANGES) { const b = document.createElement("button"); b.className = "btn"; b.id = "rg-" + n; b.textContent = n;
  b.onclick = () => applyRange(d); rgBox.appendChild(b); }
for (const k of COINS) document.getElementById("coin-" + k).onclick = () => {
  if (k === state.coin) return; state.coin = k; save(); pressed(); withLoading(() => setData(true)); };
const optHeat = document.getElementById("optHeat"), optMap = document.getElementById("optMap"), thr = document.getElementById("thr"), thrv = document.getElementById("thrv");
optHeat.checked = state.heat; optMap.checked = state.map; thr.value = state.thr; thrv.textContent = (+state.thr).toFixed(2);
optHeat.onchange = () => { state.heat = optHeat.checked; save(); heat.update(); };
optMap.onchange = () => { state.map = optMap.checked; save(); heat.update(); };
thr.oninput = () => { state.thr = +thr.value; thrv.textContent = state.thr.toFixed(2); save(); heat.update(); };
function withLoading(fn) {
  const el = document.getElementById("loading");
  if (stores[storeKey(state.coin, state.tf)]) { fn(); return; }
  el.hidden = false; setTimeout(() => { fn(); el.hidden = true; }, 30);
}
const B5 = DATA.BTCUSDT, last5 = Math.max(B5.c5.t[B5.c5.t.length - 1] + 300, B5.c1.t[B5.c1.t.length - 1] + 60);
document.getElementById("asof").textContent = "Data to " + fmtT(last5 + WIB) + " WIB · built " + fmtT(DATA.built + WIB) + " WIB";
document.getElementById("days").textContent = Math.round((B5.c5.t[B5.c5.t.length - 1] - B5.c5.t[0]) / 86400);
document.getElementById("cover").textContent = `Coverage: 5-minute candles and open interest from ${fmtT(DATA.BTCUSDT.c5.t[0] + WIB)} WIB (the heatmap starts once a full window of data exists: 1, 3 or 7 days later); 1-minute candles from ${fmtT(DATA.BTCUSDT.c1.t[0] + WIB)}; actual liquidations from ${fmtT(DATA.BTCUSDT.l5.first + WIB)}.`;
if (!DATA[state.coin]) state.coin = "BTCUSDT";
if (!TFS.some(x => x[1] === state.tf)) state.tf = 900;
if (!WINS.some(x => x[1] === state.win)) state.win = 0;
pressed();
withLoading(() => { setData(false); applyRange(3); });
new ResizeObserver(() => requestAnimationFrame(placeLabels)).observe(document.getElementById("chart"));
})();
