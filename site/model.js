/* Port of heatmap/model.py PARAMS_V6 + heatmap/snapshot.py binning (repo wahyunugi/liqmap-data).
   Rolling version: the state after candle i equals snapshot.py run with its window ending at candle i,
   because with history=0 a level's sweep and size reduction depend only on candles after it was created;
   the 24h window only decides which levels exist (created at i-287 .. i). */
var LiqModel = (function () {
  var P = { window: 288, levs: [25, 50, 100], weights: [25 / 175, 50 / 175, 100 / 175], mmr: 0.0001,
            binPct: 0.000744, shiftPct: 0.00025 };

  // snapshot.py bins_for(): box width = 0.0744% of price, anchored on a round number, display shift +0.025%
  function binsFor(price) {
    var w = P.binPct * price;
    var k = Math.pow(10, Math.floor(Math.log10(price)));
    var off = (pyRound(price / k) * k) % w;
    return { w: w, off: off, dx: P.shiftPct * price };
  }
  function pyRound(x) { // Python 3 round(): ties to even
    var f = Math.floor(x), d = x - f;
    if (d > 0.5) return f + 1; if (d < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
  }
  function binOf(price, B) { return Math.floor((price + B.dx - B.off) / B.w); }

  // Simulate every 5-minute candle. Calls onSnap(i, lp, usd, side, count) at the close of each candle i >= win.
  // win = window length in 5-minute candles: 288 (24 h) is model v6 as calibrated against CoinGlass;
  // longer windows (864 = 3 days, 2016 = 7 days) apply the same rules, keeping levels longer (not calibrated).
  function simulate(c, onSnap, win) {
    win = win || P.window;
    var n = c.t.length, cap = 4096;
    var lp = new Float64Array(cap), usd = new Float64Array(cap), side = new Uint8Array(cap), born = new Int32Array(cap);
    var m = 0;
    function grow() {
      cap *= 2;
      var a = new Float64Array(cap); a.set(lp); lp = a;
      var b = new Float64Array(cap); b.set(usd); usd = b;
      var s2 = new Uint8Array(cap); s2.set(side); side = s2;
      var d = new Int32Array(cap); d.set(born); born = d;
    }
    for (var i = 0; i < n; i++) {
      var hi = c.h[i], lo = c.l[i];
      // 1) sweep levels touched by this candle, and keep only levels created inside the window ending
      //    at this candle (for 24 h: created i-287 .. i)
      var k = 0, oldest = i - win;
      for (var j = 0; j < m; j++) {
        if ((lo <= lp[j] && lp[j] <= hi) || born[j] <= oldest) continue;
        lp[k] = lp[j]; usd[k] = usd[j]; side[k] = side[j]; born[k] = born[j]; k++;
      }
      m = k;
      // Snapshot at the close of candle i, exactly as snapshot.py sees it: the OI change of candle i
      // (= OI[i+1] - OI[i]) is not known yet, so it only shows from the next candle on.
      if (i >= win) onSnap(i, lp, usd, side, m);
      // 2) open-interest change of this candle: OI[i+1] - OI[i]
      var dv = (i + 1 < n && c.oi[i + 1] != null && c.oi[i] != null) ? c.oi[i + 1] - c.oi[i] : 0;
      var e = (c.o[i] + c.h[i] + c.l[i] + c.c[i]) / 4;
      if (dv > 0) {
        for (var q = 0; q < 3; q++) {
          var lev = P.levs[q], val = dv * e * P.weights[q]; // each side = 100% of the OI increase
          var pl = e * (1 - 1 / lev + P.mmr), ps = e * (1 + 1 / lev - P.mmr);
          if (!(lo <= pl && pl <= hi)) { if (m === cap) grow(); lp[m] = pl; usd[m] = val; side[m] = 0; born[m] = i; m++; }
          if (!(lo <= ps && ps <= hi)) { if (m === cap) grow(); lp[m] = ps; usd[m] = val; side[m] = 1; born[m] = i; m++; }
        }
      } else if (dv < 0 && m > 0) {
        // close_rule "proportional" (inherited from PARAMS_V1 in model.py): all levels shrink by the OI drop share
        var tot = c.oi[i] * e, frac = Math.max(0, 1 + dv * e / Math.max(tot, 1e-9));
        for (var j2 = 0; j2 < m; j2++) usd[j2] *= frac;
      }
    }
  }

  // Heatmap store: per candle, sorted list of (bin, longUSD, shortUSD).
  // want (optional): array/typed array of 0/1 per candle; only marked candles are stored (saves time for long windows).
  function build(c, B, win, want) {
    var n = c.t.length, start = new Int32Array(n + 1), cap = 1 << 20;
    var bins = new Int32Array(cap), lv = new Float32Array(cap), sv = new Float32Array(cap), len = 0;
    var colMax = new Float32Array(n);
    var tmp = new Map();
    var first = -1;
    simulate(c, function (i, lp, usd, side, m) {
      if (first < 0) { first = i; for (var z = 0; z <= i; z++) start[z] = 0; }
      if (want && !want[i]) { start[i] = len; start[i + 1] = len; colMax[i] = 0; return; }
      tmp.clear();
      for (var j = 0; j < m; j++) {
        var b = binOf(lp[j], B), a = tmp.get(b);
        if (!a) { a = [0, 0]; tmp.set(b, a); }
        a[side[j]] += usd[j];
      }
      var keys = Array.from(tmp.keys()).sort(function (x, y) { return x - y; });
      if (len + keys.length > cap) {
        cap *= 2;
        var nb = new Int32Array(cap); nb.set(bins); bins = nb;
        var nl = new Float32Array(cap); nl.set(lv); lv = nl;
        var ns = new Float32Array(cap); ns.set(sv); sv = ns;
      }
      start[i] = len; var mx = 0;
      for (var q = 0; q < keys.length; q++) {
        var v = tmp.get(keys[q]);
        bins[len] = keys[q]; lv[len] = v[0]; sv[len] = v[1]; len++;
        if (v[0] + v[1] > mx) mx = v[0] + v[1];
      }
      start[i + 1] = len; colMax[i] = mx;
    }, win);
    return { B: B, first: first, start: start, bins: bins, lv: lv, sv: sv, colMax: colMax, n: n };
  }

  return { P: P, binsFor: binsFor, binOf: binOf, simulate: simulate, build: build };
})();
if (typeof module !== "undefined") module.exports = LiqModel;
