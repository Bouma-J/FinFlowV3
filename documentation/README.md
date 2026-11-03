# Documentation FIN_FLOW

Plateforme SaaS multi-tenants de gestion du cycle de vie des dossiers de crédit, avec consolidation Groupe et intégration Core Banking.

## Sommaire

| Document | Contenu |
|----------|---------|
| [01 — Présentation](01-presentation.md) | Vision produit, acteurs, périmètre |
| [02 — Architecture technique](02-architecture-technique.md) | Stack, modules, flux, stockages |
| [03 — Documentation fonctionnelle](03-documentation-fonctionnelle.md) | Processus métier détaillés |
| [04 — Guide de déploiement](04-guide-deploiement.md) | Docker Compose, Kubernetes, checklist prod |
| [13 — Déploiement Ubuntu](13-guide-deploiement-ubuntu.md) | Serveur Ubuntu : outils, Docker, TLS, backups |
| [05 — Configuration](05-configuration.md) | Variables d'environnement (dont **e-mail / expéditeur**) |
| [06 — API et intégrations](06-api-et-integrations.md) | REST, JWT, CBS, OpenAPI |
| [07 — Guide utilisateur](07-guide-utilisateur.md) | Parcours opérateurs / validateurs |
| [08 — Administration et sécurité](08-administration-securite.md) | RBAC, MFA, audit, quotas |
| [09 — Montée en charge](09-montee-en-charge.md) | Court / moyen / long terme |
| [10 — Exploitation](10-exploitation-supervision.md) | Health, métriques, Celery, sauvegardes |
| [11 — Glossaire](11-glossaire.md) | Termes métier et techniques |
| [12 — Connexion au CBS](12-connexion-cbs.md) | Connecteurs, opérations, simulation, adaptateur réel |
| [14 — Backlog d’étude](14-backlog-etude.md) | 12 fiches (complet / ambitieux), hors code |

## Documents connexes

- Cahier des charges : [`../charge.txt`](../charge.txt)
- README projet : [`../README.md`](../README.md)
- Isolation multi-tenant (détail) : [`../docs/TENANT_ISOLATION.md`](../docs/TENANT_ISOLATION.md)
- Kubernetes : [`../deploy/k8s/README.md`](../deploy/k8s/README.md)
- Lifecycle S3 : [`../deploy/s3/lifecycle.json`](../deploy/s3/lifecycle.json)

## Accès rapides (Docker Compose)

| Service | URL |
|---------|-----|
| Application | http://localhost:8080 |
| API | http://localhost:8080/api/v1/ |
| Swagger | http://localhost:8080/api/docs/ |
| Admin Django | http://localhost:8080/django-admin/ |
| MinIO console | http://localhost:9001 |

## Comptes de démonstration

| Profil | Identifiant | Mot de passe |
|--------|-------------|--------------|
| Admin Groupe | `group_admin` | `FinFlow2026!` |
| Admin Filiale (si seed) | `fil01_admin` | `FinFlow2026!` |

> Activer le seed : `SEED_DEMO=1 docker compose up -d --build`

---

*Documentation générée pour FIN_FLOW — Thuin Tech. À maintenir à chaque évolution majeure.*
