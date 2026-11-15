# Opportunités Étudiants : bot Telegram d'alertes

Bot Telegram (Python, aiogram 3) qui prévient les étudiants des bourses, stages, emplois et concours correspondant à leurs mots-clés.

## État du projet

- [x] Étape 1 : structure du projet et bot connecté à Telegram
- [x] Étape 2 : base SQLite, abonnements par mots-clés, formules gratuit/premium
- [x] Étape 3 : lecture des sources (RSS/Atom, pages web), anti-doublons, alertes planifiées
- [ ] Étape 4 : mise en ligne sur un serveur

## Commandes

| Commande | Rôle |
|---|---|
| `/start` | Démarrer ou reprendre les alertes |
| `/abonner mot-clé` | Suivre un sujet (3 mots-clés en formule gratuite, 20 en premium) |
| `/mes_alertes` | Lister ses alertes |
| `/retirer mot-clé` | Supprimer une alerte |
| `/stop` | Mettre les alertes en pause |
| `/stats`, `/plan <id> <free\|premium>`, `/verifier` | Réservées à l'administrateur |

## Fonctionnement

1. Toutes les `CHECK_INTERVAL_MINUTES` minutes, le bot lit les sources listées dans `sources.json`.
2. **Premier passage d'une source** : les offres existantes sont mémorisées sans envoyer d'alerte (pas de spam au démarrage).
3. Ensuite, chaque **nouvelle offre** est comparée aux mots-clés de chaque abonné actif (titre + résumé, sans accents ni majuscules).
4. L'abonné reçoit le titre, le lien vers la source et le mot-clé qui correspond. Une même offre n'est jamais envoyée deux fois au même utilisateur.

Protections : 10 alertes maximum par utilisateur et par cycle, offres en échec d'envoi réessayées pendant 24 h, source ignorée si plus de 30 offres « nouvelles » apparaissent d'un coup (changement de structure du site), utilisateurs qui bloquent le bot désactivés automatiquement.

## Ajouter des sources (`sources.json`)

```json
[
  {"name": "Mon flux", "type": "rss", "url": "https://exemple.dz/flux.xml"},
  {"name": "Ma page d'annonces", "type": "html", "url": "https://exemple.dz/annonces",
   "link_pattern": "/annonces/", "min_title_len": 25}
]
```

- **`rss`** : flux RSS ou Atom. À privilégier quand le site en propose un.
- **`html`** : page listant des annonces. Le bot garde les liens dont le texte fait au moins `min_title_len` caractères et dont l'adresse contient `link_pattern` (expression régulière, facultative). Le fichier `robots.txt` du site est respecté.
- `"enabled": false` désactive une source sans la supprimer.

**À vérifier pour chaque site** : ses conditions d'utilisation autorisent-elles la lecture automatique ? Le bot n'envoie que le titre et le lien, jamais le contenu complet. Les sources fournies dans `sources.json` sont des **exemples à remplacer** par les vôtres.

## Installation (Windows, PowerShell)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # puis remplissez BOT_TOKEN et ADMIN_ID
python -m app.main
```

> Ne publiez jamais `.env` : il contient le token du bot (déjà exclu par `.gitignore`).

Pour tester sans attendre : envoyez `/verifier` au bot (administrateur) : il lit les sources tout de suite et affiche un rapport.

## Tests

```powershell
python -m unittest -v
```

Aucun test n'utilise internet ni Telegram.

## Structure

```
app/
├── main.py              démarrage du bot et de la planification
├── config.py            lecture du fichier .env
├── bot/
│   ├── handlers.py      commandes Telegram
│   └── notifier.py      envoi des alertes via Telegram
├── db/database.py       base SQLite (utilisateurs, mots-clés, offres, envois)
├── sources/
│   ├── rss.py           lecture RSS/Atom (bibliothèque standard)
│   ├── html_links.py    extraction de liens d'une page web
│   ├── fetcher.py       téléchargement (délai, taille max, robots.txt)
│   ├── loader.py        lit une source selon son type
│   ├── registry.py      chargement de sources.json
│   ├── models.py        Source, Item, adresses canoniques
│   ├── robots.py        règles robots.txt
│   └── errors.py        erreurs lisibles
└── services/
    ├── matching.py      mots-clés et recherche dans le texte
    ├── alerts.py        cycle : collecter, filtrer, envoyer
    └── scheduler.py     répétition des cycles
tests/                   tests unitaires
sources.json             liste des sources à surveiller
```
