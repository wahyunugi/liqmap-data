// Liquidation map totals around the current price, from the same 24-hour model the website uses (site/model.js, getStore
// in site/app.js). Cumulative USD of longs below and shorts above within 1, 2, 3, 5 and 8% of the last 5-minute close.
// Usage (after python site/build.py): node research/bands.js   -> JSON {SYMBOL: {px, t, L: [...], S: [...]}}
const fs = require("fs"), path = require("path");
const ROOT = path.join(__dirname, ".."), M = require(path.join(ROOT, "site", "model.js"));
const D = JSON.parse(fs.readFileSync(path.join(ROOT, "_site", "data.json")));
const CUTS = [0.01, 0.02, 0.03, 0.05, 0.08], out = {};
for (const sym of ["BTCUSDT", "ETHUSDT"]) {
  const c = D[sym].c5, px = c.c[c.c.length - 1];
  const st = M.build(c, M.binsFor(px), 288), s = st.n - 1, B = st.B;
  const L = CUTS.map(() => 0), S = CUTS.map(() => 0);
  for (let q = st.start[s]; q < st.start[s + 1]; q++) {
    const d = (B.off - B.dx + (st.bins[q] + 0.5) * B.w) / px - 1;   // same price of a bin as riskNow() in app.js
    CUTS.forEach((k, i) => { if (d < 0 && d >= -k) L[i] += st.lv[q]; else if (d > 0 && d <= k) S[i] += st.sv[q]; });
  }
  out[sym] = { px, t: new Date((c.t[c.t.length - 1] + 300 + 7 * 3600) * 1000).toISOString().slice(0, 16),
               L: L.map(v => Math.round(v / 1e6)), S: S.map(v => Math.round(v / 1e6)) };
}
console.log(JSON.stringify(out));
