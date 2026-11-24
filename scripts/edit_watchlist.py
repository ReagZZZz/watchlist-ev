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


def reply(text, changed):
    open(os.path.join(ROOT, "reply.md"), "w", encoding="utf-8").write(text)
    sys.exit(0 if changed else 10)


def main():
    action = os.environ.get("ACTION", "add")
    f = fields(os.environ.get("ISSUE_BODY", ""))
    t = re.sub(r"\s+", "", pick(f, "ticker")).upper()
    if not re.fullmatch(r"[A-Z0-9.\-=^]{1,20}", t):
        reply("❌ Ticker invalide : `%s`. Utilise le ticker Yahoo exact (ex. `HO.PA`, `MSFT`, `BTC-EUR`)." % t, False)
    wl = json.load(open(WL_PATH, encoding="utf-8"))
    rows = wl["rows"]
    idx = next((i for i, r in enumerate(rows) if r["t"].upper() == t), None)

    if action == "remove":
        if idx is None:
            reply("ℹ️ `%s` n'est pas dans la watchlist, rien à retirer." % t, False)
        name = rows[idx]["n"]
        del rows[idx]
        wl["updated"] = dt.date.today().isoformat()
        json.dump(wl, open(WL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        reply("✅ **%s** (`%s`) a été retiré de la watchlist. Il disparaîtra du dashboard au prochain relevé." % (name, t), True)

    if idx is not None:
        reply("ℹ️ `%s` (%s) est déjà dans la watchlist." % (t, rows[idx]["n"]), False)
    m = yahoo_meta(t)
    if not m or not m.get("regularMarketPrice"):
        reply("❌ Yahoo Finance ne trouve pas `%s`. Vérifie le suffixe de place (`.PA`, `.AS`, `.DE`…) puis rouvre une demande." % t, False)

    env = pick(f, "enveloppe").split(" ")[0] or "CTO"
    try:
        impact = int(pick(f, "impact") or 5)
    except ValueError:
        impact = 5
    name = pick(f, "nom") or m.get("longName") or m.get("shortName") or t
    these = pick(f, "thèse") or "À compléter (analyse du dimanche)."
    row = {"t": t, "n": name, "s": pick(f, "secteur") or "Autre", "e": env, "i": max(0, min(10, impact)),
           "o": pick(f, "doublon"), "th": these, "mh": "À compléter.", "r": ["À compléter", "À compléter", "À compléter"],
           "inv": "À compléter.", "added": dt.date.today().isoformat()}
    cg = pick(f, "identifiant coingecko")
    if cg:
        row["cg"] = cg.lower()
    rows.append(row)
    wl["updated"] = dt.date.today().isoformat()
    json.dump(wl, open(WL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    reply("✅ **%s** (`%s`) ajouté à la watchlist : %s, enveloppe %s, impact %d/10.\n\nCours Yahoo : %s %s. "
          "Les indicateurs et les paliers apparaîtront dans le dashboard d'ici quelques minutes. "
          "La thèse et les risques seront complétés par l'analyse du dimanche."
          % (name, t, row["s"], env, row["i"], m.get("regularMarketPrice"), m.get("currency", "")), True)


if __name__ == "__main__":
    main()
