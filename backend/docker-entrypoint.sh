#!/usr/bin/env bash
# Point d'entrée du conteneur backend :
# 1. attend que MySQL accepte les connexions (le conteneur DB peut démarrer
#    plus lentement que le backend au premier lancement) ;
# 2. crée le compte administrateur/comptable initial si absent (idempotent —
#    seed_users.py vérifie déjà l'existence de chaque compte avant insertion) ;
# 3. démarre Uvicorn.
set -euo pipefail

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-3306}"

echo "==> Attente de MySQL (${DB_HOST}:${DB_PORT})..."
until python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('${DB_HOST}', ${DB_PORT}))
except OSError:
    sys.exit(1)
"; do
  echo "    MySQL indisponible, nouvel essai dans 2s..."
  sleep 2
done
echo "==> MySQL disponible."

echo "==> Création des comptes initiaux (si absents)..."
python -m scripts.seed_users || echo "    (avertissement non bloquant : voir message ci-dessus)"

echo "==> Démarrage d'Uvicorn (${WEB_CONCURRENCY:-2} worker(s))..."
exec uvicorn app.main:app --host 0.0.0.0 --port 9000 --workers "${WEB_CONCURRENCY:-2}"
