# RSS → ODS : Une IA par jour

Script Python qui récupère **l'intégralité** du flux RSS paginé de [uneiaparjour.fr](https://www.uneiaparjour.fr/) (~1000 articles) et génère un fichier ODS structuré avec 10 colonnes :

| Titre | Description | URL | Cat. 1 | Cat. 2 | Cat. 3 | Cat. 4 | Cat. 5 | Cat. 6 | Date |
|-------|-------------|-----|--------|--------|--------|--------|--------|--------|------|

## Fonctionnement

Le script pagine automatiquement le flux WordPress (`/feed/?paged=1`, `?paged=2`, etc.) jusqu'à récupérer tous les articles. Un délai de politesse de 1 seconde est respecté entre chaque page. Les doublons sont détectés et ignorés.

## Installation

```bash
git clone https://github.com/VOTRE_UTILISATEUR/rss-to-ods.git
cd rss-to-ods
pip install -r requirements.txt
```

## Utilisation

```bash
# Récupérer TOUS les articles (pagination automatique)
python rss_to_ods.py

# Spécifier le fichier de sortie
python rss_to_ods.py -o mon_export.ods

# Limiter à 100 articles
python rss_to_ods.py --max 100

# Première page uniquement (pas de pagination)
python rss_to_ods.py --no-paginate

# Délai personnalisé entre les pages (en secondes)
python rss_to_ods.py --delay 2

# Utiliser un autre flux RSS WordPress
python rss_to_ods.py -u https://example.com/feed/ -o autre.ods
```

## Options

| Option | Description | Défaut |
|--------|-------------|--------|
| `-u`, `--url` | URL du flux RSS | `https://www.uneiaparjour.fr/feed/` |
| `-o`, `--output` | Fichier ODS de sortie | `uneiaparjour.ods` |
| `--max` | Nombre max d'articles | Tous |
| `--no-paginate` | Première page uniquement | `false` |
| `--delay` | Délai entre pages (sec.) | `1` |

## Automatisation GitHub Actions

Le workflow `.github/workflows/generate.yml` exécute le script **tous les jours à 7h UTC** et commit le fichier ODS dans `output/`.

Pour l'activer :
1. Pousser le dépôt sur GitHub
2. Aller dans **Actions** et activer les workflows
3. Le fichier `output/uneiaparjour.ods` sera automatiquement mis à jour

Lancement manuel possible via **Actions → Génération ODS depuis RSS → Run workflow**.

## Prérequis

- Python 3.10+
- **feedparser** — Parsing de flux RSS/Atom
- **odfpy** — Génération de fichiers ODS (LibreOffice/OpenDocument)

## Note sur WordPress

Le nombre d'articles par page du flux RSS dépend du réglage WordPress **Réglages → Lecture → Les flux de syndication affichent les derniers X éléments**. Si ce nombre est très faible (ex. 10), le script effectuera beaucoup de requêtes paginées. Il est recommandé de monter cette valeur à 50 ou 100 dans les réglages WordPress pour accélérer l'export.

## Licence

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr)
