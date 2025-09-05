# ClickHouse Syphon

**Bridge de synchronisation haute performance entre ClickHouse et PostgreSQL pour production.**

## 🎯 Vue d'ensemble

ClickHouse Syphon est un système de synchronisation conçu pour transférer efficacement des données de ClickHouse vers PostgreSQL avec des capacités avancées de monitoring, parallélisation et récupération d'erreurs.

## ⚡ Objectifs de Performance

-   **Performance** : 5x plus rapide que la fréquence de synchronisation
-   **Fiabilité** : Récupération automatique d'erreurs et reprises intelligentes
-   **Scalabilité** : Parallélisation et gestion optimisée de la RAM
-   **Observabilité** : Monitoring complet avec Prometheus/Grafana
-   **Opérabilité** : Déploiement Kubernetes natif avec ArgoWorkflow

## 🚀 Status du Projet

### ✅ Étape 1 - Connexions Bases de Données (TERMINÉ)

-   Configuration Pydantic avec validation de sécurité
-   Gestionnaires de connexions async (ClickHouse + PostgreSQL)
-   Context managers avec gestion d'erreurs
-   Tests complets (21/21 ✅)

### 🔄 Étapes Suivantes

-   **Étape 2** : Delta et Recovery mechanics
-   **Étape 3** : Parallélisation et load balancing
-   **Étape 4** : Logging et monitoring
-   **Étape 5** : Déploiement Kubernetes

## 🏗️ Architecture

Le système utilise une architecture moderne basée sur :

-   **Python 3.13+** avec AsyncIO
-   **ClickHouse** (source) via clickhouse-connect
-   **PostgreSQL** (cible) via asyncpg
-   **Pydantic v2** pour la configuration
-   **Polars** pour le traitement de données
-   **Prometheus** pour les métriques
-   **Kubernetes** pour l'orchestration

## 📁 Structure du Projet

```
clickhouse-syphon/
├── clickhouse_syphon/
│   ├── config.py          # Configuration Pydantic
│   ├── database.py        # Gestionnaires de connexions
│   └── __init__.py
├── tests/
│   ├── test_step1_simple.py         # Tests configuration
│   └── test_step1_connections_fixed.py  # Tests connexions
├── config/
│   └── tables.yaml        # Configuration des tables
├── docs/
│   ├── ARCHITECTURE.md    # Documentation architecture complète
│   └── STEP1_COMPLETE.md  # Status étape 1
└── pyproject.toml         # Configuration uv/Python
```

## 🚀 Quick Start

### Prérequis

-   Python 3.13+
-   uv (gestionnaire de paquets)
-   ClickHouse accessible
-   PostgreSQL accessible

### Installation

```bash
# Cloner le repository
git clone <repo-url>
cd clickhouse-syphon

# Installer les dépendances
uv sync

# Configurer l'environnement
cp config/tables.yaml.example config/tables.yaml
# Éditer config/tables.yaml avec vos paramètres

# Lancer les tests
uv run python -m pytest tests/ -v
```

### Configuration

```yaml
# config/tables.yaml
clickhouse:
    host: "localhost"
    port: 9000
    username: "default"
    password: "your-password"

postgresql:
    host: "localhost"
    port: 5432
    username: "postgres"
    password: "your-password"
    database: "target_db"

tables:
    - name: "events"
      source_table: "events"
      target_table: "events_sync"
      sync_mode: "incremental"
      timestamp_column: "created_at"
```

## 🧪 Tests

```bash
# Tous les tests
uv run python -m pytest tests/ -v

# Tests spécifiques
uv run python -m pytest tests/test_step1_simple.py -v
uv run python -m pytest tests/test_step1_connections_fixed.py -v
```

## 📊 Monitoring

Le système expose des métriques Prometheus :

-   `syphon_sync_duration_seconds` - Durée des synchronisations
-   `syphon_rows_processed_total` - Lignes traitées
-   `syphon_sync_errors_total` - Erreurs de synchronisation
-   `syphon_active_workers` - Workers actifs

## 🐳 Déploiement

### Docker

```bash
# Construction de l'image
docker build -t clickhouse-syphon .

# Exécution
docker run -v $(pwd)/config:/app/config clickhouse-syphon
```

### Kubernetes

```bash
# Déploiement avec Helm
helm install syphon ./charts/clickhouse-syphon
```

## 📚 Documentation

-   [Architecture Complète](docs/ARCHITECTURE.md) - Diagrammes C4, algorithmes et patterns
-   [Étape 1 Status](docs/STEP1_COMPLETE.md) - Détails de l'implémentation actuelle

## 🤝 Contribution

1. Fork le projet
2. Créer une branche feature
3. Commit les changements
4. Pousser vers la branche
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

**Développé avec ❤️ pour une synchronisation de données haute performance**
