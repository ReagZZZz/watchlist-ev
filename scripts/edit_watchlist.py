#!/usr/bin/env python3
"""Ajoute ou retire un titre de watchlist.json à partir d'un formulaire GitHub (issue).

Entrées (variables d'environnement) : ISSUE_BODY, ACTION ("add" ou "remove").
Sortie : écrit le message de réponse dans reply.md et code retour 0 si la watchlist a changé,
10 si rien n'a changé (erreur de saisie, doublon…).
"""
import json, os, re, sys, urllib.parse, urllib.request
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WL_PATH = os.path.join(ROOT, "watchlist.json")
UA = {"User-Agent": "Mozilla/5.0 (watchlist-ev robot)", "Accept": "application/json"}
NONE = {"", "_no response_", "none", "aucun", "aucune"}


def fields(body):
    """Le formulaire GitHub produit des blocs « ### Libellé » suivis de la valeur."""
    out, key = {}, None
    for line in (body or "").splitlines():
        if line.startswith("### "):
            key = line[4:].strip().lower()
            out[key] = ""
        elif key is not None:
            out[key] = (out[key] + "\n" + line).strip()
    return {k: ("" if v.strip().lower() in NONE else v.strip()) for k, v in out.items()}


def pick(f, prefix):
    for k, v in f.items():
        if k.startswith(prefix):
            return v
    return ""


def yahoo_meta(t):
    url = "https://query2.finance.yahoo.com/v8/finance/chart/%s?range=5d&interval=1d" % urllib.parse.quote(t)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            m = json.loads(r.read().decode())["chart"]["result"][0]["meta"]
            return m
    except Exception:
        return None


EU_PEA = {"PAR", "AMS", "GER", "MIL", "MCE", "BRU", "LIS", "ISE", "HEL", "VIE"}
EU_EEE = {"STO", "CPH", "OSL", "ICE"}
SECONDARY = {"FRA", "BER", "MUN", "STU", "DUS", "HAM", "HAN", "MEX", "BUE", "NEO", "IOB", "SAO", "PNK", "OTC", "TLO", "CXE", "AQS", "DXE", "EUX"}
OK_TYPES = {"EQUITY", "ETF", "CRYPTOCURRENCY"}
SECTORS = [("semiconductor", "Semi-conducteurs"), ("aerospace", "Défense & Aéro"), ("defense", "Défense & Aéro"),
           ("luxury", "Luxe"), ("apparel", "Luxe"), ("auto", "Mobilité"), ("credit services", "Paiements"),
           ("software", "Logiciels"), ("information technology", "Logiciels"), ("internet", "Big Tech"),
           ("beverage", "Agro"), ("food", "Agro"), ("packaged", "Agro"), ("drug", "Santé"), ("biotech", "Santé"),
           ("medical", "Santé"), ("health", "Santé"), ("oil", "Énergie"), ("energy", "Énergie"), ("utilities", "Énergie"),
           ("bank", "Finance"), ("insurance", "Finance"), ("asset management", "Finance"), ("capital markets", "Finance"),
           ("financial", "Finance"), ("real estate", "Immobilier"), ("reit", "Immobilier"), ("basic materials", "Matières premières"),
           ("chemical", "Matières premières"), ("industrials", "Industrie"), ("technology", "Logiciels"),
           ("consumer", "Conso"), ("communication", "Conso")]


def get_json(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def search(q):
    j = get_json("https://query2.finance.yahoo.com/v1/finance/search?q=%s&quotesCount=10&newsCount=0&lang=fr-FR&region=FR"
                 % urllib.parse.quote(q))
    return [x for x in (j or {}).get("quotes", []) if x.get("quoteType") in OK_TYPES and x.get("symbol")]


def resolve(q, env_pref):
    """Retourne (ticker, meta, candidat, autres) pour un nom d'entreprise ou un ticker."""
    cands = search(q)
    # Ticker exact déjà valide ?
    direct = yahoo_meta(q.upper()) if re.fullmatch(r"[A-Za-z0-9.\-=^]{1,20}", q) else None
    if direct and direct.get("regularMarketPrice") and direct.get("instrumentType") in OK_TYPES | {None}:
        sym = direct.get("symbol", q.upper())
        cand = next((c for c in cands if c["symbol"] == sym), {"symbol": sym, "quoteType": direct.get("instrumentType"),
                                                                 "exchange": direct.get("exchangeName", "")})
        return sym, direct, cand, [c for c in cands if c["symbol"] != sym][:3]
    if not cands:
        return None, None, None, []

    def score(ic):
        i, c = ic
        ex = c.get("exchange", "")
        sc = i * 1.0
        if ex in SECONDARY:
            sc += 20
        if c.get("quoteType") == "CRYPTOCURRENCY":
            sc -= 5
        if env_pref in ("PEA", "PEA*") and ex in EU_PEA | EU_EEE:
            sc -= 8
        return sc
    ranked = [c for _, c in sorted(enumerate(cands), key=score)]
    best = ranked[0]
    sym = best["symbol"]
    if best.get("quoteType") == "CRYPTOCURRENCY":
        base = sym.split("-")[0]
        sym = base + "-EUR"
    m = yahoo_meta(sym)
    if (not m or not m.get("regularMarketPrice")) and sym != best["symbol"]:
        sym = best["symbol"]; m = yahoo_meta(sym)
    return sym, m, best, [c for c in ranked[1:] if c["symbol"] != sym][:3]


def auto_env(cand, sym, name):
    qt, ex = cand.get("quoteType"), cand.get("exchange", "")
    if qt == "CRYPTOCURRENCY" or sym.endswith("-EUR") and qt is None:
        return "Crypto"
    if qt == "ETF":
        return "PEA" if "PEA" in (name or "").upper() else "CTO"
    if ex in EU_PEA:
        return "PEA"
    if ex in EU_EEE:
        return "PEA*"
    return "CTO"


def auto_sector(cand):
    if cand.get("quoteType") == "CRYPTOCURRENCY":
        return "Crypto"
    if cand.get("quoteType") == "ETF":
        return "ETF & couverture"
    txt = (str(cand.get("industry", "")) + " " + str(cand.get("sector", ""))).lower()
    for k, v in SECTORS:
        if k in txt:
            return v
    return "Autre"


def reply(text, changed):
    open(os.path.join(ROOT, "reply.md"), "w", encoding="utf-8").write(text)
    sys.exit(0 if changed else 10)


def main():
    action = os.environ.get("ACTION", "add")
    f = fields(os.environ.get("ISSUE_BODY", ""))
    raw = (pick(f, "entreprise") or pick(f, "ticker")).strip()
    if not raw or len(raw) > 60:
        reply("❌ Indique le nom de l'entreprise (ex. « Hermès », « Microsoft »).", False)
    t = re.sub(r"\s+", "", raw).upper()
    wl = json.load(open(WL_PATH, encoding="utf-8"))
    rows = wl["rows"]
    idx = next((i for i, r in enumerate(rows) if r["t"].upper() == t), None)
    if idx is None:
        low = raw.lower()
        idx = next((i for i, r in enumerate(rows) if low in r["n"].lower()), None)

    if action == "remove":
        if idx is None:
            reply("ℹ️ « %s » n'est pas dans la watchlist, rien à retirer." % raw, False)
        name, t = rows[idx]["n"], rows[idx]["t"]
        del rows[idx]
        wl["updated"] = dt.date.today().isoformat()
        json.dump(wl, open(WL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        reply("✅ **%s** (`%s`) a été retiré de la watchlist. Il disparaîtra du dashboard au prochain relevé." % (name, t), True)

    env_in = pick(f, "enveloppe").split(" ")[0]
    env_in = "" if env_in in ("", "Auto") else env_in
    sym, m, cand, others = resolve(raw, env_in)
    if not sym or not m or not m.get("regularMarketPrice"):
        alts = ", ".join("`%s` (%s, %s)" % (c["symbol"], c.get("shortname") or c.get("longname", ""), c.get("exchDisp", c.get("exchange", ""))) for c in others) or "aucune"
        reply("❌ Je n'ai pas trouvé de titre coté pour « %s ». Autres correspondances : %s. Réessaie avec un autre nom." % (raw, alts), False)
    t = sym.upper()
    hit = next((r for r in rows if r["t"].upper() == t), None)
    if hit:
        reply("ℹ️ **%s** (`%s`) est déjà dans la watchlist." % (hit["n"], t), False)
    name = m.get("longName") or cand.get("longname") or cand.get("shortname") or m.get("shortName") or t
    name = re.sub(r"\s+(Société en commandite par actions|Société anonyme|S\.?A\.?|SE|N\.?V\.?|AG|plc|PLC|Inc\.?|Corporation|Corp\.?|Ltd\.?|Limited|Holdings?|S\.p\.A\.?|A/S|ASA|AB \(publ\))\s*$", "", name).strip(" ,") or name
    env = env_in or auto_env(cand, t, name)
    sec_in = pick(f, "secteur")
    sec = sec_in if sec_in and sec_in != "Auto" else auto_sector(cand)
    try:
        impact = int(pick(f, "impact") or 5)
    except ValueError:
        impact = 5
    row = {"t": t, "n": name, "s": sec, "e": env, "i": max(0, min(10, impact)),
           "o": pick(f, "doublon"), "th": pick(f, "thèse") or "À compléter (analyse du dimanche).", "mh": "À compléter.",
           "r": ["À compléter", "À compléter", "À compléter"], "inv": "À compléter.", "added": dt.date.today().isoformat()}
    if env == "Crypto":
        row["cg"] = (cand.get("shortname") or name).split(" ")[0].lower()
    rows.append(row)
    wl["updated"] = dt.date.today().isoformat()
    json.dump(wl, open(WL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    place = cand.get("exchDisp") or m.get("fullExchangeName") or cand.get("exchange", "")
    alts = "\n".join("- `%s` : %s (%s)" % (c["symbol"], c.get("longname") or c.get("shortname", ""), c.get("exchDisp", c.get("exchange", ""))) for c in others)
    msg = ("✅ **%s** ajouté à la watchlist sous le ticker `%s` (%s).\n\n"
           "- Secteur : %s · Enveloppe : %s · Impact : %d/10\n- Cours : %s %s\n\n"
           "Les indicateurs et les paliers apparaîtront dans le dashboard d'ici quelques minutes ; "
           "la thèse et les risques seront complétés par l'analyse du dimanche."
           % (name, t, place, sec, env, row["i"], m.get("regularMarketPrice"), m.get("currency", "")))
    if env in ("PEA", "PEA*"):
        msg += "\n\n⚠️ Enveloppe déduite de la place de cotation : vérifie que la société a bien son siège dans l'UE/EEE."
    if alts:
        msg += "\n\nCe n'est pas le bon titre ? Ouvre une demande « Retirer » pour `%s`, puis « Ajouter » avec le nom exact. Autres correspondances :\n%s" % (t, alts)
    reply(msg, True)


if __name__ == "__main__":
    main()
