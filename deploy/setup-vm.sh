#!/usr/bin/env bash
# Provisionnement d'une VM Ubuntu 22.04 (pense pour l'instance gratuite
# e2-micro de Google Cloud, mais fonctionne sur tout VPS Ubuntu) pour
# heberger Compta-IA en entier : MySQL + backend FastAPI + frontend
# (buildé et servi par Nginx), tout sur la meme machine.
#
# Usage : copier ce script sur la VM (scp), puis :
#   chmod +x setup-vm.sh && sudo ./setup-vm.sh
#
# Hypotheses :
# - Ubuntu 22.04 LTS (fonctionne aussi bien en ARM64 qu'en x86_64)
# - Le depot git du projet est deja clone dans /opt/compta-ia
#   (sinon, decommenter la section GIT_CLONE ci-dessous)
# - Executer en tant que root (sudo)
# - RAM limitee (1 Go sur un e2-micro) : ce script cree un fichier swap de
#   4 Go des le depart pour eviter tout OOM pendant l'installation ou
#   l'execution du pipeline OCR/IA.
set -euo pipefail

APP_DIR="/opt/compta-ia"
APP_USER="compta"
DB_NAME="compta_ia_db"
DB_USER="compta_user"
DB_PASS="$(openssl rand -hex 16)"   # genere une fois, affiche a la fin
SECRET_KEY="$(openssl rand -hex 32)"
SWAP_FILE="/swapfile"
SWAP_SIZE_GB="4"   # indispensable sur une instance a 1 Go de RAM (ex. GCP e2-micro)

echo "==> Creation d'un fichier swap (${SWAP_SIZE_GB} Go)"
# Sur une instance a faible RAM (typiquement 1 Go, comme le e2-micro gratuit
# de Google Cloud), l'installation de PyTorch/EasyOCR et leur execution
# saturent la memoire sans swap et font tuer les processus par l'OOM killer.
if [ ! -f "$SWAP_FILE" ]; then
  fallocate -l "${SWAP_SIZE_GB}G" "$SWAP_FILE" || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=$((SWAP_SIZE_GB * 1024))
  chmod 600 "$SWAP_FILE"
  mkswap "$SWAP_FILE"
  swapon "$SWAP_FILE"
  grep -q "$SWAP_FILE" /etc/fstab || echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
fi
# Swappiness basse : on ne veut du swap qu'en dernier recours (plus lent
# qu'une vraie RAM), pas pour un usage courant.
sysctl -w vm.swappiness=10
grep -q "vm.swappiness" /etc/sysctl.conf || echo "vm.swappiness=10" >> /etc/sysctl.conf

echo "==> Mise a jour du systeme et installation des paquets requis"
apt-get update -y
apt-get upgrade -y
apt-get install -y \
  python3.10 python3.10-venv python3-pip \
  mysql-server \
  tesseract-ocr tesseract-ocr-fra \
  nginx \
  git curl build-essential \
  libgl1 libglib2.0-0   # dependances runtime d'OpenCV headless

echo "==> Installation de Node.js 20 (pour builder le frontend)"
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

echo "==> Creation de l'utilisateur systeme dedie a l'application"
id -u "$APP_USER" &>/dev/null || useradd -r -m -d "/home/$APP_USER" -s /bin/bash "$APP_USER"

# --- GIT_CLONE (decommenter et adapter si le code n'est pas deja present) ---
# mkdir -p "$APP_DIR"
# git clone https://github.com/<votre-compte>/<votre-repo>.git "$APP_DIR"
# chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

if [ ! -d "$APP_DIR/backend" ]; then
  echo "ERREUR : $APP_DIR/backend introuvable."
  echo "Clonez d'abord votre depot dans $APP_DIR, ou decommentez la section GIT_CLONE ci-dessus."
  exit 1
fi

echo "==> Configuration de MySQL (base + utilisateur dedies)"
mysql -u root <<SQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "==> Chargement du schema et du plan comptable"
mysql -u root "${DB_NAME}" < "$APP_DIR/database/schema.sql"
mysql -u root "${DB_NAME}" < "$APP_DIR/database/seed_accounts.sql"

echo "==> Environnement virtuel Python + dependances backend"
cd "$APP_DIR/backend"
python3.10 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
./venv/bin/python -m spacy download fr_core_news_md

echo "==> Fichier .env de production"
cat > "$APP_DIR/backend/.env" <<ENV
DATABASE_URL=mysql+pymysql://${DB_USER}:${DB_PASS}@localhost:3306/${DB_NAME}
SECRET_KEY=${SECRET_KEY}
ACCESS_TOKEN_EXPIRE_MINUTES=480
UPLOAD_DIR=./storage/uploads
MODELS_DIR=./storage/models
OCR_LANGUAGES=fr,en
OCR_FALLBACK_THRESHOLD=0.55
OCR_REJECT_THRESHOLD=0.40
DEFAULT_VAT_RATE=0.20
DEFAULT_CURRENCY=MGA
RETRAIN_CORRECTION_THRESHOLD=50
ENV
mkdir -p "$APP_DIR/backend/storage/uploads" "$APP_DIR/backend/storage/models"

echo "==> Creation du compte administrateur initial"
cd "$APP_DIR/backend" && ./venv/bin/python -m scripts.seed_users

echo "==> Build du frontend (fichiers statiques)"
cd "$APP_DIR/frontend"
npm ci
npm run build

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

echo "==> Installation du service systemd du backend"
cp "$APP_DIR/deploy/compta-ia-backend.service" /etc/systemd/system/
sed -i "s#/opt/compta-ia#${APP_DIR}#g; s#compta_user_placeholder#${APP_USER}#g" \
  /etc/systemd/system/compta-ia-backend.service
systemctl daemon-reload
systemctl enable --now compta-ia-backend

echo "==> Installation de la configuration Nginx"
cp "$APP_DIR/deploy/nginx-compta-ia.conf" /etc/nginx/sites-available/compta-ia
sed -i "s#/opt/compta-ia#${APP_DIR}#g" /etc/nginx/sites-available/compta-ia
ln -sf /etc/nginx/sites-available/compta-ia /etc/nginx/sites-enabled/compta-ia
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "=================================================================="
echo " Deploiement termine."
echo " Mot de passe MySQL genere pour ${DB_USER} : ${DB_PASS}"
echo " (deja inscrit dans ${APP_DIR}/backend/.env -- notez-le par securite)"
echo ""
echo " Identifiants de connexion initiaux (voir backend/scripts/seed_users.py) :"
echo "   admin@compta-ia.mg / Admin2026!"
echo "   comptable@compta-ia.mg / Compta2026!"
echo " -> A changer immediatement apres la premiere connexion."
echo ""
echo " Application accessible sur : http://<ip-externe-de-la-vm>/"
echo " Pensez a ouvrir le port 80 (et 443 si HTTPS) via une regle de"
echo " pare-feu GCP (gcloud compute firewall-rules create ...)."
echo "=================================================================="
