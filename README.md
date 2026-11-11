# Opportunités Étudiants : bot Telegram d'alertes

Bot Telegram (Python, aiogram 3) qui prévient les étudiants des bourses, stages, emplois et concours correspondant à leurs mots-clés.

## État du projet

- [x] Étape 1 : structure du projet et bot connecté à Telegram
- [x] Étape 2 : base SQLite, abonnements par mots-clés, formules gratuit/premium, tests
- [ ] Étape 3 : lecture des sources (RSS, pages web) et envoi des alertes
- [ ] Étape 4 : mise en ligne sur un serveur

## Commandes

| Commande | Rôle |
|---|---|
| `/start` | Démarrer ou reprendre les alertes |
| `/abonner mot-clé` | Suivre un sujet (3 mots-clés en formule gratuite, 20 en premium) |
| `/mes_alertes` | Lister ses alertes |
| `/retirer mot-clé` | Supprimer une alerte |
| `/stop` | Mettre les alertes en pause |
| `/stats`, `/plan <id> <free\|premium>` | Réservées à l'administrateur |

## Installation (Windows, PowerShell)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # puis remplissez BOT_TOKEN et ADMIN_ID
python -m app.main
```

> Ne publiez jamais `.env` : il contient le token du bot (déjà exclu par `.gitignore`).

## Tests

```powershell
python -m unittest -v
```

## Structure

```
app/
├── main.py            démarrage du bot
├── config.py          lecture du fichier .env
├── bot/handlers.py    commandes Telegram
├── db/database.py     base SQLite (utilisateurs, mots-clés, offres vues)
├── sources/rss.py     lecture des sources (étape 3)
└── services/
    ├── matching.py    nettoyage des mots-clés et recherche dans le texte
    └── scheduler.py   vérifications planifiées (étape 3)
tests/                 tests unitaires
```
