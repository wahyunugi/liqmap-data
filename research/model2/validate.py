"""
Uji di luar sampel: terapkan hasil final_fit.json (campuran leverage + skala per rentang) TANPA DIUBAH ke screenshot baru.
Daftar screenshot uji di refs_test.json, contoh:
  {"BTC_D_1030": {"img": "ref/xxx.png", "p_top": 88799, "p_bot": 73116, "cbar": 18.52e6, "span_h": 24, "sym": "BTCUSDT", "range": "D"}}
  range: D = 24 jam, W = 1 minggu, M = 1 bulan.
Dua skor per gambar: "beku" (campuran dan skala dari 29 Okt) dan "skala bebas" (campuran beku, hanya skala dicari ulang).
    python research/model2/validate.py [ladder]      # ladder bawaan: lengkap_14
"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg  # noqa: E402
from fit import COL_STEP, cg_matrix  # noqa: E402
from joint import score  # noqa: E402
from final_fit import RES, matrices  # noqa: E402
from resolution import resample  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import inputs  # noqa: E402


def main():
    ladder = sys.argv[1] if len(sys.argv) > 1 else "lengkap_14"
    fit = json.load(open(os.path.join(HERE, "final_fit.json")))[ladder]
    tiers, w, f = fit["tiers"], np.array(fit["w"]), fit["f"]
    refs = json.load(open(os.path.join(HERE, "refs_test.json")))
    dfcache = {}
    for name, r in refs.items():
        ref = cg.Ref(r["img"], r["p_top"], r["p_bot"], r["cbar"], r["span_h"], r.get("sym", "BTCUSDT"))
        if ref.sym not in dfcache:
            dfcache[ref.sym] = inputs.load(ref.sym)
        df5 = dfcache[ref.sym]; k = r["range"]
        g = cg.load(ref); err, t_end, span = cg.align(ref, g, df5)
        d = df5[df5.t % (300 * RES[k]) == 0].index.min(); dfk = resample(df5.iloc[d:].reset_index(drop=True), RES[k])
        cols = list(range(0, g["W"], COL_STEP)); Y, edges = cg_matrix(ref, g, cols); m = np.isfinite(Y)
        X = matrices(dfk, t_end, span, cols, g["W"], edges, tiers)
        A = np.stack([X[L][m] for L in tiers], 1); y = Y[m]
        p = A @ w
        frozen = score(p * f[k], y)
        a = float(p @ y / max(p @ p, 1e-30))
        free = score(p * a, y)
        print(json.dumps(dict(gambar=name, rentang=k, sumbu_waktu_selisih_usd=round(err), beku=frozen,
                              skala_bebas=free, skala_ditemukan=round(a, 3), skala_29okt=round(f[k], 3))), flush=True)


if __name__ == "__main__":
    main()
