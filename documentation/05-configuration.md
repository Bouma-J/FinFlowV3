# 05 — Configuration

Les variables sont lues via `django-environ` (`backend/config/settings/`).  
Référence commentée : `backend/.env.example`.  
En Compose, beaucoup sont injectées dans `docker-compose.yml` (`x-backend-env`).

## 1. Django / sécurité

| Variable | Défaut / notes |
|----------|----------------|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` (Compose) ou `dev` |
| `DJANGO_SECRET_KEY` | **Obligatoire** en prod |
| `DJANGO_DEBUG` | `False` en prod |
| `DJANGO_ALLOWED_HOSTS` | Liste séparée par virgules |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Origines frontend |
| `DJANGO_SECURE_SSL_REDIRECT` | `True` en prod TLS |
| `DJANGO_SECURE_HSTS_SECONDS` | Domaine : `31536000`. IP Let’s Encrypt : `604800`. IP auto-signé / HTTP : `0` |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` sur un nom de domaine uniquement |
| `DJANGO_SECURE_HSTS_PRELOAD` | `True` sur un nom de domaine uniquement — **jamais** sur une IP |

## 2. Base de données

| Variable | Notes |
|----------|-------|
| `DATABASE_URL` | `postgres://user:pass@host:5432/db` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Attente entrypoint |
| `DB_CONN_MAX_AGE` | Secondes (60 typique ; **0** avec PgBouncer transaction) |

Sans `DATABASE_URL` en settings de base → SQLite local (dev laptop uniquement).

## 3. JWT

| Variable | Défaut |
|----------|--------|
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | 30 |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | 1 |

`ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True` (code).

## 4. Stockage GED (S3 / MinIO)

| Variable | Exemple Compose |
|----------|-----------------|
| `STORAGE_BACKEND` | `s3` ou `local` |
| `AWS_ACCESS_KEY_ID` | `minioadmin` |
| `AWS_SECRET_ACCESS_KEY` | `minioadmin` |
| `AWS_STORAGE_BUCKET_NAME` | `finflow-documents` |
| `AWS_S3_ENDPOINT_URL` | `http://minio:9000` (réseau Docker) |
| `AWS_S3_CUSTOM_DOMAIN` | `localhost:9000` (navigateur) |
| `AWS_S3_REGION_NAME` | `us-east-1` |
| `AWS_S3_ADDRESSING_STYLE` | `path` |
| `AWS_S3_URL_PROTOCOL` | `http:` |
| `AWS_QUERYSTRING_AUTH` | `True` |

Les fichiers GED / pieces clients sont lus via **URL présignées MinIO**
(navigateur → MinIO direct). `AWS_S3_ENDPOINT_URL` reste l’adresse Docker
interne (`http://minio:9000`) pour le backend ; `AWS_S3_CUSTOM_DOMAIN` est
l’hôte public utilisé dans la signature. Un proxy API reste disponible en
repli (logos, stockage local, ouverture sécurisée).

Plafonds applicatifs (settings) : `GED_MAX_UPLOAD_SIZE_MB`, `GED_ALLOWED_EXTENSIONS`.

## 5. Celery / Redis / cache

| Variable | Notes |
|----------|-------|
| `CELERY_BROKER_URL` | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` |
| `REDIS_CACHE_URL` | optionnel ; sinon dérivé du broker (`/2`) |

En `dev.py` : `CELERY_TASK_ALWAYS_EAGER=True` (pas de worker requis).

## 6. E-mail — configuration **par filiale** (recommandé)

Chaque filiale configure son propre SMTP dans l’interface d’administration.  
Les e-mails d’**identifiants** et d’**alertes de circuit** de cette filiale partent alors avec **son** compte mail.

### 6.1 Où configurer (UI)

1. Se connecter en **admin Groupe** (ou admin filiale).  
2. Sélectionner la **filiale** dans la barre supérieure.  
3. Menu **Administration → Alertes e-mail**.  
4. Renseigner le bloc **Serveur SMTP de la filiale** :

| Champ UI | Description |
|----------|-------------|
| Serveur SMTP | Ex. `smtp.gmail.com` |
| Port | `587` (TLS) ou `465` (SSL) |
| Identifiant SMTP | Compte d’envoi (souvent = adresse From) |
| Mot de passe SMTP | Mot de passe ou « App Password » (laisser vide pour conserver l’existant) |
| Expéditeur (From) | Optionnel : adresse seule. Affichage auto : `NOREPLY {filiale} <adresse>` |
| Répondre à | Optionnel |
| TLS / SSL | Cocher l’un ou l’autre selon le port |

5. **Enregistrer**, puis **Tester l’envoi** vers une adresse réelle.

API :
- `GET/PATCH /api/v1/notification-settings/current/`
- `POST /api/v1/notification-settings/current/test/` `{ "to": "…" }`

### 6.2 Ce qui utilise le SMTP filiale

| Type d’e-mail | Source SMTP |
|---------------|-------------|
| Mot de passe temporaire (création / régénération) | SMTP de la **filiale de l’utilisateur** |
| Alertes workflow (étape, fin, rejet, renvoi) | SMTP de la **filiale du dossier** |
| Utilisateur **Groupe** (sans filiale) | Repli sur la config **globale** (`.env`) |

Si le serveur SMTP filiale (hôte + identifiant) est **vide**, FIN_FLOW bascule sur les variables globales `EMAIL_*` / `DEFAULT_FROM_EMAIL`.

### 6.3 Alertes de circuit (mêmes écran)

Sur la même page : activer/désactiver les notifications d’étape, fin de circuit (validé → contrats ; rejeté ; renvoyé pour correction — alerte à l’initiateur), copie à l’e-mail de la filiale.

### 6.4 Repli global (Docker / `.env`) — optionnel

Utile pour la démo, les comptes Groupe, ou un SMTP unique de plateforme.

| Variable | Exemple | Notes |
|----------|---------|-------|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | `console` = logs seulement |
| `EMAIL_HOST` / `PORT` / `USE_TLS` / `USE_SSL` | `smtp.gmail.com` / `587` / `True` / `False` | |
| `EMAIL_HOST_USER` / `PASSWORD` | compte SMTP | |
| `DEFAULT_FROM_EMAIL` | `FIN_FLOW <noreply@…>` | Expéditeur de repli |
| `FRONTEND_BASE_URL` | `https://finflow.exemple.com` | Liens dans les mails |

Fichier `.env` à la racine + :

```bash
docker compose up -d --force-recreate backend worker beat
```

Mode démo sans SMTP réel :

```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

Référence : [`backend/.env.example`](../backend/.env.example).

### 6.5 Exemple Gmail (filiale)

1. Compte Google → 2FA activée → **Mot de passe d’application**.  
2. Dans **Alertes e-mail** de la filiale :  
   - Serveur `smtp.gmail.com`, port `587`, TLS coché  
   - Identifiant = adresse Gmail  
   - Mot de passe = App Password  
   - Expéditeur = la même adresse  
3. Envoyer un e-mail de test.

#### Antivirus Windows (Avast / Norton)

Les boucliers « Mail Shield » / « Web Shield » interceptent souvent SMTP et
provoquent des erreurs du type :

- `SSL: CERTIFICATE_VERIFY_FAILED` / certificat « Avast Web/Mail Shield »
- `connect error 10060` / `Cannot connect to SMTP server …:587`

**Correctifs (par ordre préféré) :**
1. Désactiver temporairement le Mail Shield, ou exclure `smtp.gmail.com`
   (ports 587 et 465).
2. Exporter la CA de l’antivirus dans `backend/certs/ca-bundle.crt` puis
   `docker compose up -d --build backend worker`.
3. En démo locale uniquement : `SMTP_SSL_VERIFY=0` (déjà le défaut Compose).
   En production Ubuntu : `SMTP_SSL_VERIFY=1`.

Docker Desktop fait passer le trafic du conteneur par la pile réseau
Windows, donc l’antivirus hôte s’applique aussi aux envois FIN_FLOW.

### 6.6 Vérification

1. Configurer le SMTP filiale + test OK.  
2. Créer un utilisateur de cette filiale → le mail d’identifiants doit arriver avec l’expéditeur filiale.  
3. Consulter le **journal des envois** en bas de la page Alertes e-mail.

## 7. Métier / scale

| Variable | Défaut | Rôle |
|----------|--------|------|
| `GROUP_CONSOLIDATION_CURRENCY` | `XOF` | Devise consolidation |
| `SEED_DEMO` | `0` (Compose) | Seed au boot |
| `AUDIT_RETENTION_DAYS` | `365` | Purge audit (`0` = off) |
| `REPORTING_SNAPSHOT_MAX_AGE_SECONDS` | `3600` | Fraîcheur snapshots |
| `DASHBOARD_CACHE_TTL` | `45` | Cache dashboard |
| `ME_CACHE_TTL` | `60` | Cache profil |
| `CATALOG_CACHE_TTL` | `120` | Cache produits |
| `TENANT_ISOLATION_MODE` | `shared` | `shared` \| `schema` (cible) |

## 8. Supervision

| Variable | Notes |
|----------|-------|
| `SENTRY_DSN` | Active Sentry si non vide |
| `SENTRY_ENVIRONMENT` | ex. `production` |
| `SENTRY_TRACES_SAMPLE_RATE` | ex. `0.1` |

## 9. Frontend

| Variable | Notes |
|----------|-------|
| `VITE_API_BASE_URL` | Défaut `/api/v1` (même origine via Nginx) |

## 10. Bonnes pratiques

- Ne jamais committer de `.env` avec secrets réels.  
- Aligner `AWS_S3_CUSTOM_DOMAIN` sur le hostname joignable depuis le navigateur.  
- Séparer les index Redis (broker / result / cache).  
- Documenter toute variable ajoutée ici **et** dans `.env.example`.
