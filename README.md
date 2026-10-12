# eb-finance

Outils d'extraction et d'analyse des données Shopify, de chargement dans
Snowflake et de mise à jour du statut de stock des produits.

## Structure du dépôt

```text
.
├── data/                      # CSV et JSON d'extraction, aperçus et journaux de publication
├── logs/                      # Journaux d'exécution
├── src/
│   ├── extract-orders.py      # Extraction Shopify des commandes
│   ├── extract-products.py    # Extraction Shopify des produits et variantes
│   ├── load-shopify-to-snowflake.py
│   ├── publish-stock-status.py
│   ├── run_pipeline.py        # Orchestration du pipeline de stock
│   ├── update-stock-status.py # Génération de l'aperçu de stock
│   └── utils.py               # Configuration et fonctions partagées
├── env.bash                  # Configuration bash locale (ignorée par Git)
├── env.ps1                   # Configuration PowerShell locale (ignorée par Git)
├── env_exemple.bash          # Modèle de configuration bash
├── env.ps1.example           # Modèle de configuration PowerShell
├── requirements.txt
└── README.md
```

Les fichiers générés dans `data/`, les journaux, les fichiers d'environnement
locaux et les clés privées ne sont pas suivis par Git.

## Installation

Créer et activer l'environnement virtuel, puis installer les dépendances.

### Bash (macOS / Linux / Git Bash / WSL)

```bash
python -m venv .venv
source .venv/bin/activate
cp env_exemple.bash env.bash
```

Renseigner les valeurs dans `env.bash`, charger la configuration dans chaque
nouveau terminal, puis installer les dépendances :

```bash
source env.bash
pip install -r requirements.txt
```

### Variables d'environnement

Dans `env.bash`, remplacer les exemples par les valeurs de l'application
Shopify et du compte Snowflake :

| Variable | Valeur à renseigner |
| --- | --- |
| `SHOPIFY_CLIENT_ID` | Client ID de l'application Shopify. |
| `SHOPIFY_CLIENT_SECRET` | Client secret de l'application Shopify. |
| `SHOPIFY_SHOP` | Nom de la boutique sans `.myshopify.com`; facultatif, la valeur par défaut est `epiphanieboutique`. |
| `SNOWFLAKE_ACCOUNT` | Identifiant du compte Snowflake, généralement au format `organisation-compte`. |
| `SNOWFLAKE_USER` | Utilisateur Snowflake autorisé à accéder aux tables Shopify. |
| `SNOWFLAKE_PRIVATE_KEY` | Contenu PEM de la clé privée Snowflake non chiffrée. Le modèle lit ce contenu depuis un fichier `.p8` local. |
| `SNOWFLAKE_ROLE` | Rôle Snowflake à utiliser; facultatif, valeur par défaut `ROLE_SHOPIFY`. |
| `SNOWFLAKE_WAREHOUSE` | Warehouse Snowflake à utiliser. |

La base et le schéma Snowflake sont facultatifs : ils prennent par défaut les
valeurs `SHOPIFY` et `PUBLIC`. Garder `env.bash` et la clé privée hors de Git;
ne jamais remplacer les exemples par de vrais secrets dans le modèle
`env_exemple.bash`.

## Utilisation

Les commandes sont à exécuter depuis la racine du dépôt, avec l'environnement
activé et les variables d'environnement chargées.

### Pipeline de statut de stock

```bash
python src/run_pipeline.py
```

Le pipeline extrait le catalogue complet et les commandes complètes, génère
`data/stock_status_preview.csv`, puis publie les statuts dans les descriptions
Shopify. Les chaussures sont résumées par pointure; les autres produits par
quantité totale. **Cette commande effectue des écritures sur Shopify.** Pour
simuler la publication sans modifier Shopify, exécuter les étapes séparément :

```bash
python src/extract-products.py --full
python src/update-stock-status.py
python src/publish-stock-status.py --dry-run
```

Pour limiter un test réel à quelques produits, le script de publication accepte
`--limit N`, par exemple `python src/publish-stock-status.py --limit 3`.

### Extraction et chargement Snowflake

Sans option, les extractions sont incrémentales et utilisent les watermarks
Snowflake. `--full` force une extraction complète sans consulter Snowflake.

```bash
python src/extract-products.py
python src/extract-orders.py
python src/load-shopify-to-snowflake.py
```

Les CSV d'extraction et de statut ainsi que le journal de publication sont
écrits sous `data/`. Les journaux d'exécution sont écrits sous `logs/`.
