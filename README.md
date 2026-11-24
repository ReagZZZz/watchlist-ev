# Watchlist EV+

Dashboard de suivi de ma watchlist (actions PEA/CTO, ETF, crypto) avec prix d'entrée en 3 paliers, score EV+ et alertes. Les données de marché se mettent à jour seules, sans ordinateur allumé.

**Ceci n'est pas un conseil en investissement** : c'est un outil de tri et de discipline personnel.

## Comment ça tourne

| Élément | Rôle |
|---|---|
| `.github/workflows/update.yml` | Lance le robot toutes les 2 h en semaine (7h-21h UTC) et une fois le week-end |
| `scripts/fetch.py` | Récupère les cours Yahoo Finance (CoinGecko en secours pour la crypto), calcule MM50/MM200/RSI/ATR, paliers P1-P3, statut et score EV+ |
| `data/data.json` | Instantané lu par le dashboard (même origine : ni proxy, ni CORS) |
| `data/signals.csv` | Journal de chaque passage en zone 🟢, pour mesurer la qualité du score dans le temps |
| `watchlist.json` | Liste des titres, enveloppes, scores d'impact, thèses et risques |
| `fair_values.json` | Valeurs intrinsèques issues de l'analyse du dimanche (le P2 devient fondamental) |
| `index.html` | Le dashboard, publié sur GitHub Pages |

## Mise en route (une seule fois)

1. **Settings → Pages** : Source = *Deploy from a branch*, branche `main`, dossier `/ (root)`. Le dashboard sera sur `https://reagzzzz.github.io/watchlist-ev/`.
2. **Actions** → *Mise à jour des cours* → **Run workflow** pour le premier remplissage.
3. *(Optionnel)* Notifications sur le téléphone : installer l'app **ntfy**, s'abonner à un sujet au nom impossible à deviner (ex. `ev-paul-7k3q9x`), puis **Settings → Secrets and variables → Actions → New repository secret** : `NTFY_TOPIC` = ce nom.

## Ajouter ou retirer un titre

**Depuis le téléphone** : bouton « ＋ Ajouter un titre » du dashboard, ou onglet *Issues* → *New issue* → **Ajouter un titre à la watchlist** (ou **Retirer un titre**). Il suffit de taper le nom de l'entreprise : le robot trouve le ticker sur Yahoo (en privilégiant la cotation européenne si tu choisis le PEA), déduit l'enveloppe et le secteur, met à jour `watchlist.json`, relance le calcul des cours, répond en commentaire et ferme la demande. Seules les demandes du propriétaire du dépôt sont traitées.

**À la main** : 
Modifier `watchlist.json` (ticker Yahoo exact, avec le suffixe de place : `.PA`, `.AS`, `.DE`, `.MI`, `.ST`, `.CO`, `.OL`, `.SW`, `.L`, `.T`, `.HK`, `.KS`). Pour une crypto : ticker `XXX-EUR` et champ `cg` = identifiant CoinGecko.

## Format de `fair_values.json`

```json
{
  "SU.PA": { "fv_eur": 265, "range": [240, 290], "date": "2026-11-29", "method": "DCF + PER historique" }
}
```

## Limites

- L'API Yahoo n'est pas officielle : elle peut changer ou limiter les appels. En cas d'échec, le ticker est listé dans `failed` et le dashboard garde le dernier cours connu.
- Les dépôts publics affichent leur contenu : ce dépôt ne contient que des données de marché et la watchlist, aucun montant détenu.
