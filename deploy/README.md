# Déploiement de Compta-IA (Google Cloud Free Tier)

Ce dossier contient tout ce qu'il faut pour déployer l'application (base de
données + backend + frontend) sur une seule machine virtuelle Linux
**gratuite à vie** : l'instance `e2-micro` du niveau gratuit de Google Cloud
(Compute Engine "Always Free").

## Pourquoi une seule VM plutôt qu'un PaaS gratuit classique ?

Le pipeline IA embarque des dépendances lourdes (PyTorch via EasyOCR,
spaCy, XGBoost) qui dépassent largement les limites mémoire des offres
gratuites type Render/Railway/PythonAnywhere/InfinityFree (512 Mo à 1 Go,
souvent sans processus long-terme ni root). Une VM dédiée, même modeste,
est la seule option gratuite qui permette d'installer et de faire tourner
ce genre de stack sans restriction de temps d'exécution.

## Attention : contrainte mémoire réelle de l'e2-micro

L'instance gratuite `e2-micro` ne dispose que de **1 Go de RAM** (contre
plusieurs Go sur l'offre ARM Always Free d'Oracle Cloud, si celle-ci
devient accessible pour vous). Pour que le pipeline OCR/IA tienne quand
même dans cette contrainte, ce dossier applique trois mesures :

1. **Un fichier swap de 4 Go**, créé automatiquement par `setup-vm.sh` —
   indispensable, sans lui EasyOCR/PyTorch font planter la VM (OOM killer)
   dès la première facture traitée.
2. **Un seul worker Uvicorn** (`compta-ia-backend.service`) — chaque worker
   charge sa propre copie des modèles en mémoire ; en charger deux
   doublerait l'empreinte mémoire pour rien sur une machine mono-utilisateur
   (soutenance, démonstration).
3. **Des délais Nginx plus longs** (180 s) — un cœur `e2-micro` partagé
   traite l'OCR nettement plus lentement qu'une VM dédiée.

Avec le swap, l'application fonctionne, mais chaque facture prendra
plusieurs secondes de plus à traiter qu'en local. Si les performances sont
insuffisantes pour votre usage, la seule vraie solution est de migrer vers
une VM avec plus de RAM (payante sur GCP, ou Oracle Cloud Always Free si
disponible pour vous).

## Étapes manuelles (à faire une seule fois, hors de portée d'un script)

1. **Créer le projet et activer Compute Engine**
   - Créer un compte sur [console.cloud.google.com](https://console.cloud.google.com)
     (carte bancaire demandée pour vérification, mais le niveau gratuit
     n'entraîne aucun prélèvement tant que vous restez dans ses limites).
   - Créer un projet, puis activer l'API "Compute Engine" pour ce projet.

2. **Créer l'instance `e2-micro` gratuite**
   - L'instance gratuite n'est disponible que dans certaines régions :
     `us-west1`, `us-central1` ou `us-east1` (Oregon, Iowa, Caroline du
     Sud). Choisir l'une de ces régions, sinon la gratuité ne s'applique
     pas.
   - Image : **Ubuntu 22.04 LTS**.
   - Disque : jusqu'à 30 Go de disque persistant standard (HDD) inclus
     gratuitement — ne pas choisir de disque SSD, qui sort du niveau
     gratuit.
   - Via la console, ou en ligne de commande avec `gcloud` :
     ```bash
     gcloud compute instances create compta-ia-vm \
       --zone=us-central1-a \
       --machine-type=e2-micro \
       --image-family=ubuntu-2204-lts \
       --image-project=ubuntu-os-cloud \
       --boot-disk-size=30GB \
       --boot-disk-type=pd-standard
     ```
   - Noter l'adresse IP externe de l'instance (visible dans la console ou
     via `gcloud compute instances list`).

3. **Ouvrir les ports réseau (règles de pare-feu)**
   ```bash
   gcloud compute firewall-rules create allow-http \
     --allow=tcp:80 --direction=INGRESS --target-tags=http-server
   gcloud compute instances add-tags compta-ia-vm --tags=http-server
   ```
   (Ajouter `tcp:443` de la même façon si vous configurez un nom de domaine
   avec HTTPS plus tard. Le port 22/SSH est déjà ouvert par défaut sur
   GCP.)

4. **Copier le projet sur la VM**
   ```bash
   # Depuis votre machine locale
   gcloud compute scp --recurse D:/Etude/son compta-ia-vm:/tmp/compta-ia --zone=us-central1-a
   gcloud compute ssh compta-ia-vm --zone=us-central1-a
   sudo mv /tmp/compta-ia /opt/compta-ia
   ```
   (Alternative recommandée à terme : héberger le code sur GitHub et faire
   un `git clone` directement sur la VM — plus simple pour les mises à jour
   futures, et évite de retransférer les gros dossiers `node_modules`/
   `venv` qui ne doivent de toute façon pas être copiés.)

5. **Lancer le script de provisionnement**
   ```bash
   cd /opt/compta-ia/deploy
   chmod +x setup-vm.sh
   sudo ./setup-vm.sh
   ```
   Ce script crée d'abord le fichier swap (essentiel sur 1 Go de RAM), puis
   installe MySQL, Python, Node.js, Tesseract, Nginx, crée la base de
   données, construit le frontend, installe le service systemd du backend
   et la configuration Nginx. Il affiche à la fin le mot de passe MySQL
   généré et les identifiants de connexion initiaux.

   Sur un `e2-micro`, cette étape est nettement plus lente que sur une VM
   plus puissante (installation de PyTorch notamment) : comptez 15 à 30
   minutes, contre quelques minutes ailleurs.

6. **Vérifier**
   - Ouvrir `http://<ip-externe-de-la-vm>/` dans un navigateur.
   - Se connecter avec `admin@compta-ia.mg` / `Admin2026!` puis **changer
     immédiatement ce mot de passe** (créer un nouveau compte admin et
     désactiver celui-ci, ou changer son mot de passe si l'interface le
     permet).

## Fichiers de ce dossier

| Fichier | Rôle |
|---|---|
| `setup-vm.sh` | Script d'installation complet (swap, MySQL, Python, Node, Nginx, systemd) |
| `compta-ia-backend.service` | Service systemd qui garde le backend FastAPI actif en permanence (1 seul worker, adapté à la RAM limitée) |
| `nginx-compta-ia.conf` | Sert le frontend compilé et redirige `/api` vers le backend, avec des délais adaptés à un CPU partagé |

## Mises à jour ultérieures

Après une modification du code (backend ou frontend) :
```bash
cd /opt/compta-ia
git pull                                   # ou re-copier les fichiers modifiés
sudo systemctl restart compta-ia-backend   # si le backend a changé
cd frontend && npm run build               # si le frontend a changé (Nginx sert directement dist/)
```

## HTTPS (optionnel, recommandé si vous avez un nom de domaine)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d votre-domaine.mg
```
Certbot configure automatiquement Nginx pour rediriger en HTTPS et
renouvelle le certificat tout seul.

## Limites connues de ce type d'hébergement

- **RAM très limitée (1 Go)** : voir la section dédiée ci-dessus. C'est la
  contrainte la plus importante de ce déploiement.
- **Quota réseau sortant limité** : le niveau gratuit de GCP inclut 1 Go de
  trafic sortant par mois vers la plupart des destinations (le trafic vers
  la Chine et l'Australie n'est pas inclus). Pour une démonstration ou un
  usage à faible volume, cela suffit largement ; au-delà, le trafic
  excédentaire est facturé.
- Pas de sauvegarde automatique de la base de données : pensez à planifier
  un `mysqldump` régulier (ex. via une tâche cron) vers un stockage externe.
- Une seule instance : en cas de panne de la VM, l'application est
  indisponible le temps de la relancer (pas de haute disponibilité).
- Les modèles ré-entraînés et les factures importées sont stockés sur le
  disque de la VM (`backend/storage/`) : à inclure dans vos sauvegardes.
