# eb-finance

Outil d'analyse des données Shopify et calcul des bénéfices/coûts.

## Installation

### Créer l'environnement virtuel
```bash
python -m venv .venv
```

### Activer l'environnement (macOS/Linux)
```bash
source .venv/bin/activate
source env.bash
```

### Installer les dépendances
```bash
pip install -r requirements.txt
```

## Utilisation

Exécuter les scripts d'extraction :
```bash
python src/extract-orders.py 
python src/extract-products.py
python src/order-calculate-benefit-cost.py
python src/stats-products.py
```