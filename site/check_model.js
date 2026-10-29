// Cek otomatis: heatmap dari model.js (dipakai website) harus sama dengan heatmap/snapshot.py (Python).
// Jalankan setelah: python site/build.py && python heatmap/snapshot.py <SIMBOL> --no-plot
// Pemakaian: node site/check_model.js   -> keluar dengan kode 1 bila ada selisih
const fs = require("fs"), path = require("path");
const ROOT = path.join(__dirname, ".."), M = require("./model.js");
const D = JSON.parse(fs.readFileSync(path.join(ROOT, "_site", "data.json")));
let ok = true;
for (const s of ["BTCUSDT", "ETHUSDT"]) {
  const c = D[s].c5, dir = path.join(ROOT, "output", s);
  const files = fs.readdirSync(dir).filter(f => f.endsWith("_levels.csv")).sort();
  const f = files[files.length - 1], m = f.match(/_(\d{4})(\d\d)(\d\d)_(\d\d)(\d\d)WIB/);
  const tEnd = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4] - 7, +m[5]) / 1000, i = c.t.indexOf(tEnd - 300);
  if (i < 0) { console.log(s, "candle", f, "tidak ada di data.json"); ok = false; continue; }
  const B = M.binsFor(c.c[i]), js = new Map();
  M.simulate(c, (k, lp, usd, side, n) => { if (k !== i) return;
    for (let j = 0; j < n; j++) { const key = M.binOf(lp[j], B) + "|" + (side[j] ? "short" : "long"); js.set(key, (js.get(key) || 0) + usd[j]); } });
  const rows = fs.readFileSync(path.join(dir, f), "utf8").trim().split("\n"), hd = rows.shift().split(","), py = new Map();
  for (const r of rows) { const o = Object.fromEntries(r.split(",").map((v, k) => [hd[k], v]));
    py.set(Math.round((+o.price_low - B.off) / B.w) + "|" + o.side, +o.usd); }
  let err = 0, diff = 0;
  for (const [k, v] of py) { if (!js.has(k)) diff++; else err = Math.max(err, Math.abs(js.get(k) - v)); }
  for (const k of js.keys()) if (!py.has(k)) diff++;
  const good = diff === 0 && err < 0.01;
  ok = ok && good;
  console.log(`${s} ${f}: ${py.size} level Python, ${js.size} level JS, beda kotak ${diff}, selisih USD maks ${err.toFixed(4)} -> ${good ? "SAMA" : "BEDA"}`);
}
process.exit(ok ? 0 : 1);
