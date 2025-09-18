# ClickHouse Syphon

## Objectifs

Bridge en Python pour gérer la synchronisation de plusieurs tables de ClickHouse vers PostgreSQL.

## Description du fonctionnement du bridge

Ce bridge devra inclure :

### Fonctionnalités principales

## core

-   ✅fonctionnement par config yaml ou arguments en ligne de commande.
-   Trois modes de synchro :
    -   ✅mode "**incrémental**" : reprend depuis la dernière synchronisation en ce basant sur une colonne de type timestamp ou id auto-incrémenté de la table cible.
    -   mode "**rewind**" : reprend depuis une date/ID spécifique et recopie toutes les données jusqu'à la dernière dans la table cible.
    -   mode "**full**": recopie toutes les données de la table source vers la table cible.
-   deploiement par argocd et argoworflow.
-   fonctionnement dry-run pour tester les configs sans exécuter les synchronisations. Ce mode permet de valider la configuration et de simuler les opérations sans modifier les données réelles. Doit fournir un rapport détaillé des actions qui auraient été effectuées.

## déploiement

-   ✅utilisation d''un fichier de config yaml pour l'execution
-   2 types de périodes de synchronisation pour l'instant (mais doit etre configurable) :
    -   périodicité courte (20 minutes)
    -   périodicité longue (24 heures)
-   ✅application sous docker/kubernetes
-   ✅configuration via des fichiers de configuration YAML/JSON
-   CI/CD avec GitHub Actions

### Approche

Création du bridge généralisé basé sur la compréhension du travail spécifique réalisé pour en extraire des règles générales.

## Livrable attendu

### Bridge opérationnel en production

-   Configuration via fichiers de configuration
-   CI/CD respectant le Trunk-based développement avec l'équipe Infra si besoin
-   Tests unitaires et tests d'intégration
-   Monitoring en place en collaboration avec l'équipe Infra

### Documentation fournie

-   Modèle C4
-   Limites identifiées et améliorations possibles
