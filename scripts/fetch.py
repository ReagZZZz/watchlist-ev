#!/usr/bin/env python3
"""Robot Watchlist EV+ : cours Yahoo Finance (+ CoinGecko en secours crypto),
indicateurs, paliers d'entrée, statut, score EV+, journal des signaux, notifications.

Sorties :
  data/data.json     instantané complet lu par le dashboard
  data/signals.csv   journal des passages en zone 🟢 (pour mesurer la qualité du score)
  data/state.json    statut précédent de chaque ligne (détection des changements)
"""
import csv, json, math, os, sys, time, datetime as dt
import urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WL = json.load(open(os.path.join(ROOT, "watchlist.json"), encoding="utf-8"))["rows"]
FV_PATH = os.path.join(ROOT, "fair_values.json")   # valeurs intrinsèques (analyse du dimanche)
FV = json.load(open(FV_PATH, encoding="utf-8")) if os.path.exists(FV_PATH) else {}
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (watchlist-ev robot)", "Accept": "application/json"}
SKIP = {"SPACEX", "ANTHROPIC", "FNOX.ST"}
CCYS = ["USD", "CHF", "DKK", "NOK", "SEK", "JPY", "KRW", "HKD", "GBP"]


def get(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # 429 / réseau : on réessaie avec un délai croissant
            if k == tries - 1:
                print("ÉCHEC", url[:90], e, file=sys.stderr)
                return None
            time.sleep(2 + 3 * k)


def calc(C, H, L, p):
    if len(C) < 20:
        return None
    avg = lambda n: sum(C[-n:]) / len(C[-n:])
    g = l = 0.0
    for k in range(1, 15):
        d = C[k] - C[k - 1]
        g += max(d, 0); l += max(-d, 0)
    g /= 14; l /= 14
    for k in range(15, len(C)):
        d = C[k] - C[k - 1]
        g = (g * 13 + max(d, 0)) / 14; l = (l * 13 + max(-d, 0)) / 14
    rsi = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    TR = [max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1])) for k in range(1, len(C))]
    atr = sum(TR[:14]) / 14
    for x in TR[14:]:
        atr = (atr * 13 + x) / 14
    return dict(p=p, prev=C[-2], ma50=avg(50), ma200=avg(200), hi52=max(H), lo52=min(L), rsi=rsi, atr=atr)


def yahoo(t):
    j = get("https://query2.finance.yahoo.com/v8/finance/chart/%s?range=1y&interval=1d" % urllib.parse.quote(t))
    try:
        R = j["chart"]["result"][0]; m = R["meta"]; q = R["indicators"]["quote"][0]
    except Exception:
        return None
    C, H, L = [], [], []
    for c, h, l in zip(q["close"], q["high"], q["low"]):
        if None not in (c, h, l):
            C.append(c); H.append(h); L.append(l)
    cur, div = m.get("currency", "EUR"), 1
    if cur in ("GBp", "GBX"):
        cur, div = "GBP", 100
    r = calc(C, H, L, m.get("regularMarketPrice") or C[-1])
    if not r:
        return None
    r = {k: v / div if k != "rsi" else v for k, v in r.items()}
    r["c"] = cur
    r["mt"] = m.get("regularMarketTime")
    return r


def coingecko(cid):
    j = get("https://api.coingecko.com/api/v3/coins/%s/market_chart?vs_currency=eur&days=365&interval=daily" % cid)
    if not j or "prices" not in j:
        return None
    C = [x[1] for x in j["prices"]]
    r = calc(C, C, C, C[-1])
    if r:
        r["c"] = "EUR"
    return r


def main():
    now = dt.datetime.now(dt.timezone.utc)
    fx = {"EUR": 1.0}
    for c in CCYS:
        r = yahoo("EUR%s=X" % c)
        if r:
            fx[c] = r["p"]
    rows, fails = {}, []
    for w in WL:
        t = w["t"]
        if t in SKIP:
            continue
        r = yahoo(t)
        if not r and w.get("cg"):
            r = coingecko(w["cg"]); time.sleep(3)
        if not r:
            fails.append(t); continue
        f = fx.get(r["c"])
        if not f:
            fails.append(t); continue
        e = {k: (v / f if k in ("p", "prev", "ma50", "ma200", "hi52", "lo52", "atr") else v) for k, v in r.items()}
        P = e["p"]
        p1 = e["ma50"] if P > e["ma50"] else e["ma200"] if P > e["ma200"] else P - e["atr"]
        fv = FV.get(t, {}).get("fv_eur")
        p2 = fv * 0.825 if fv else min(p1, e["ma200"]) - 1.5 * e["atr"]
        p3 = min(e["lo52"], p2 * 0.9)
        d1 = (P / p1 - 1) * 100
        st = "go" if (P <= p1 or e["rsi"] < 30) else "near" if d1 <= 5 else "no"
        ev = None
        if w.get("i") is not None:
            dd = min(max((1 - P / e["hi52"]) / 0.4, 0), 1)
            rs = min(max((70 - e["rsi"]) / 40, 0), 1)
            pr = min(max(1 - d1 / 20, 0), 1)
            ev = round(100 * (0.4 * w["i"] / 10 + 0.25 * dd + 0.2 * rs + 0.15 * pr))
        rows[t] = {**{k: round(v, 6) if isinstance(v, float) else v for k, v in e.items()},
                   "c_native": r["c"], "p_native": r["p"], "p1": round(p1, 6), "p2": round(p2, 6),
                   "p3": round(p3, 6), "d1": round(d1, 2), "st": st, "ev": ev, "fv": fv}
        time.sleep(0.4)

    # Journal des signaux + notifications sur changement de statut
    sp = os.path.join(DATA, "state.json")
    first = not os.path.exists(sp)
    prev = json.load(open(sp)) if not first else {}
    new_go = [] if first else [t for t, r in rows.items() if r["st"] == "go" and prev.get(t) != "go"]
    lp = os.path.join(DATA, "signals.csv")
    newfile = not os.path.exists(lp)
    with open(lp, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if newfile:
            w.writerow(["date_utc", "ticker", "statut", "prix_eur", "p1", "rsi", "ev"])
        for t in new_go:
            r = rows[t]
            w.writerow([now.strftime("%Y-%m-%d %H:%M"), t, "go", round(r["p"], 4), round(r["p1"], 4), round(r["rsi"]), r["ev"]])
    json.dump({t: r["st"] for t, r in rows.items()}, open(sp, "w"))

    out = {"generated_utc": now.isoformat(timespec="seconds"), "fx": fx, "rows": rows, "failed": fails}
    json.dump(out, open(os.path.join(DATA, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("OK %d lignes, %d échecs, %d nouveaux signaux" % (len(rows), len(fails), len(new_go)))

    topic = os.environ.get("NTFY_TOPIC")
    names = {w["t"]: w["n"] for w in WL}
    if topic and new_go:
        lines = ["%s : %.2f € (P1 %.2f €, RSI %d)" % (names[t], rows[t]["p"], rows[t]["p1"], rows[t]["rsi"]) for t in new_go[:10]]
        req = urllib.request.Request("https://ntfy.sh/" + topic, data="\n".join(lines).encode(),
                                     headers={"Title": "Watchlist EV+ : %d signal(s) vert(s)" % len(new_go), "Tags": "chart_with_upwards_trend"})
        try:
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print("ntfy:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
