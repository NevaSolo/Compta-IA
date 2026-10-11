# Déploiement Docker de Compta-IA (serveur Contabo)

Ce document explique comment déployer Compta-IA (base de données + backend
+ frontend) sur un serveur Contabo (ou tout VPS Ubuntu/Debian), entièrement
conteneurisé avec Docker Compose. Trois conteneurs : `db` (MySQL 8),
`backend` (FastAPI + pipeline OCR/NLP/ML), `frontend` (Nginx servant le
build React et reverse-proxyant `/api` vers le backend).

## Pourquoi Docker ici (contrairement au déploiement VM nue documenté dans `deploy/`)

Un serveur Contabo dédié dispose de sa propre RAM/CPU garantis (pas de
partage ni de quota gratuit à ménager comme sur un free-tier cloud) :
Docker apporte surtout de la **reproductibilité** (même environnement en
local et en production) et de l'**isolation** (MySQL, backend et frontend
ne polluent pas le système hôte, mise à jour d'un composant sans toucher
aux autres).

## Prérequis sur le serveur

- Ubuntu 22.04 (ou toute distribution récente)
- Docker Engine + le plugin Docker Compose

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # puis se reconnecter (ou `newgrp docker`)
```

## 1. Copier le projet sur le serveur

Le plus simple est de passer par un dépôt Git (GitHub/GitLab) :

```bash
git clone https://github.com/<votre-compte>/compta-ia.git
cd compta-ia
```

Alternative sans Git, depuis votre machine locale :
```bash
scp -r D:/Etude/son user@<ip-contabo>:/home/user/compta-ia
```
(Ne copiez pas `backend/venv/` ni `frontend/node_modules/` — inutiles ici,
tout est reconstruit dans les images Docker.)

## 2. Configurer les secrets

```bash
cp .env.example .env
nano .env
```

Renseignez :
- `MYSQL_ROOT_PASSWORD` — mot de passe MySQL (fort, unique)
- `SECRET_KEY` — générez-le avec `openssl rand -hex 32`

Ce fichier `.env` n'est **jamais** commité (déjà exclu par `.gitignore`).

## 3. Ouvrir le port 80 (et 443 si HTTPS plus tard)

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow OpenSSH
sudo ufw enable
```
(Si votre pare-feu Contabo passe par leur interface web plutôt que `ufw`,
ouvrez les mêmes ports là-bas.)

## 4. Construire et lancer

```bash
docker compose up -d --build
```

Premier démarrage : MySQL initialise automatiquement le schéma et le plan
comptable malgache (fichiers dans `database/`, montés dans
`/docker-entrypoint-initdb.d/`), puis le backend crée les comptes
utilisateurs initiaux dès qu'il peut se connecter à la base. Comptez 2 à 5
minutes la première fois (construction de l'image backend, dont
EasyOCR/PyTorch).

Identifiants initiaux (à changer immédiatement après la première
connexion) :
```
admin@compta-ia.mg / Admin2026!
comptable@compta-ia.mg / Compta2026!
```

## 5. Vérifier

```bash
docker compose ps                 # les 3 services doivent être "healthy"/"running"
docker compose logs -f backend    # suivre le démarrage du backend
```

Ouvrez `http://<ip-de-votre-contabo>/` dans un navigateur.

## Commandes utiles

| Action | Commande |
|---|---|
| Voir les logs en direct | `docker compose logs -f [service]` |
| Redémarrer un service | `docker compose restart backend` |
| Arrêter tout | `docker compose down` |
| Arrêter et **supprimer les données** | `docker compose down -v` ⚠️ |
| Reconstruire après modif du code | `docker compose up -d --build` |
| Ouvrir un shell dans le backend | `docker compose exec backend bash` |
| Exécuter une commande ponctuelle | `docker compose exec backend python -m scripts.seed_users` |

## Mises à jour ultérieures

```bash
git pull
docker compose up -d --build
```
Les données (MySQL, factures importées, modèles entraînés) survivent à la
reconstruction : elles vivent dans des volumes Docker nommés
(`mysql_data`, `backend_storage`, `easyocr_cache`), pas dans les images.

## Sauvegardes

```bash
# Base de données
docker compose exec db mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" compta_ia_db > backup_$(date +%Y%m%d).sql

# Factures importées et modèles entraînés
docker run --rm -v compta-ia_backend_storage:/data -v $(pwd):/backup \
  alpine tar czf /backup/storage_$(date +%Y%m%d).tar.gz -C /data .
```
Planifiez ces deux commandes via une tâche cron régulière, et copiez les
archives générées vers un stockage externe au serveur.

## HTTPS (recommandé si vous avez un nom de domaine)

Le plus simple avec ce montage Docker est d'ajouter un reverse-proxy
Caddy ou Traefik devant le conteneur `frontend` (gestion automatique des
certificats Let's Encrypt). Dites-le-moi si vous voulez que je l'ajoute au
`docker-compose.yml` — cela demande d'exposer un domaine pointant vers
l'IP du serveur au préalable.

## Limites connues

- Pas de haute disponibilité (une seule instance de chaque service) : en
  cas de panne du serveur, l'application est indisponible le temps de la
  relancer.
- Les sauvegardes ne sont pas automatiques par défaut — voir la section
  ci-dessus, à planifier vous-même (cron).

## Mettre à jour une base existante (migrations)

`database/schema.sql` n'est exécuté qu'au **tout premier démarrage** du conteneur
MySQL (volume vide). Pour une base déjà en service, les évolutions du schéma sont
dans `database/migrations/` et s'appliquent à la main, une seule fois, dans l'ordre :

```bash
docker compose exec -T db mysql --default-character-set=utf8mb4 -uroot -p"$MYSQL_ROOT_PASSWORD" \
  compta_ia_db < database/migrations/001_ocr_engine_pdf_text.sql
```

`001` ajoute le moteur `PDF_TEXT` (lecture directe du texte des PDF numériques) :
sans lui, le traitement d'un PDF numérique échoue à l'enregistrement du résultat de lecture.
