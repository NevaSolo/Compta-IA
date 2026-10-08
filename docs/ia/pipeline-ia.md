# Spécification du pipeline d'Intelligence Artificielle

Système intelligent de génération automatique des écritures comptables — PCG malgache 2005, TVA 20 %, factures fournisseurs multilingues, exécution CPU.

---

## Vue d'ensemble

```
Facture PDF/Image
  → [1] Prétraitement image (OpenCV)
  → [2] OCR (EasyOCR principal, Tesseract fallback)
  → [3] Détection de langue + nettoyage du texte
  → [4] Extraction d'entités (regex multilingues + spaCy NER)
  → [5] Contrôles de cohérence arithmétique
  → [6] Classification du type d'opération (ML)
  → [7] Moteur de règles PCG (gabarits) + suggestion de comptes (ML)
  → [8] Score de confiance global
  → [9] Validation humaine → corrections stockées
  → [10] Réentraînement périodique versionné
```

Chaque étape est implémentée derrière un port du domaine (`OCREngine`, `EntityExtractor`, `OperationClassifier`) — interchangeable et testable isolément.

---

## Étape 1 — Prétraitement image (OpenCV)

Objectif : maximiser la qualité d'entrée de l'OCR. Chaîne appliquée :

| # | Opération | Algorithme | Justification |
|---|---|---|---|
| 1 | Conversion PDF → image | pdf2image (Poppler), 300 DPI | 300 DPI = optimum précision/temps pour l'OCR |
| 2 | Niveaux de gris | `cv2.cvtColor` BGR→GRAY | Les moteurs OCR travaillent en luminance |
| 3 | Redressement (deskew) | Transformée de Hough sur les lignes + rotation de l'angle médian | Une inclinaison > 2° dégrade fortement la segmentation des lignes |
| 4 | Débruitage | `cv2.fastNlMeansDenoising` (non-local means) | Préserve les contours des caractères contrairement au flou gaussien |
| 5 | Binarisation adaptative | `cv2.adaptiveThreshold` (gaussien, fenêtre 31 px) | Robuste aux éclairages non uniformes des photos de smartphone ; un seuil global (Otsu) échoue sur les ombres |
| 6 | Contrôle qualité | Score de netteté = variance du Laplacien | Si < seuil (~100), la facture est marquée « qualité faible » dès l'entrée |

Décision : le prétraitement est **paramétrable et journalisé** (les paramètres appliqués sont stockés avec l'`OcrResult`) pour la reproductibilité des expériences du mémoire.

---

## Étape 2 — OCR multilingue avec fallback

**Moteur principal : EasyOCR** (détecteur CRAFT + reconnaissance CRNN, mode CPU).

- Un `Reader` par **groupe de langues compatible**, chargé au démarrage et gardé en mémoire :
  - groupe latin par défaut : `['fr','en']` (couvre le français, l'anglais, et lit correctement les libellés malgaches — alphabet latin) ;
  - groupes additionnels activables par configuration (ex. `['ar','en']`, `['ch_sim','en']`) — contrainte EasyOCR : les alphabets non latins ne se combinent qu'avec l'anglais.
- La langue est choisie à l'upload par l'utilisateur, sinon groupe latin par défaut ; après la première passe, une détection de langue (bibliothèque `langdetect` sur le texte extrait) peut déclencher une seconde passe avec un autre groupe.
- Sortie exploitée : liste de blocs `{texte, boîte englobante (4 points), confiance ∈ [0,1]}`.

**Fallback : Tesseract 5 (LSTM)** — déclenché si la confiance moyenne EasyOCR < **0,55** ou si moins de 10 mots sont détectés. Si le fallback fait mieux (confiance moyenne supérieure), son résultat est retenu ; le moteur utilisé est enregistré (`ocr_results.engine`).

**Échec définitif** : si les deux moteurs restent sous 0,40 de confiance moyenne → statut `ERROR`, facture signalée « illisible », saisie manuelle proposée. Le système refuse de propager des données douteuses.

*Évaluation prévue au mémoire* : comparaison EasyOCR vs Tesseract sur le corpus de test — CER/WER (taux d'erreur caractère/mot) et taux d'extraction correcte des champs clés.

---

## Étape 3 — Détection de langue et nettoyage du texte

1. **Détection de langue** (`langdetect`) sur le texte brut → stockée sur `invoices.language`, transmise au NLP.
2. **Corrections d'erreurs OCR contextuelles** (uniquement dans les zones numériques identifiées) : `O→0`, `l/I→1`, `S→5`, `B→8` lorsque le token est majoritairement numérique. Jamais de correction dans les zones textuelles (risque de corrompre les noms propres).
3. **Normalisation des nombres** : gestion des séparateurs de milliers usuels à Madagascar (espace, point) et de la virgule décimale — `1 234 567,50` → `1234567.50`. Ambiguïté point/virgule résolue par la position (un séparateur suivi de 3 chiffres = milliers).
4. **Normalisation des dates** : formats `JJ/MM/AAAA`, `JJ-MM-AA`, `JJ mois AAAA` (mois en fr/en/mg : janvier/January/Janoary…) → ISO 8601.
5. Suppression des artefacts (caractères isolés de faible confiance, lignes de pointillés).

---

## Étape 4 — Extraction d'entités (approche hybride)

Principe : **regex déterministes pour les entités à format fixe, NER statistique pour les entités contextuelles**. Chaque entité extraite conserve : valeur brute, valeur normalisée, confiance, méthode (`REGEX`/`NER`), zone source sur l'image (`source_block`).

### 4a. Entités par règles (précision quasi parfaite, multilingue par construction)

| Entité | Stratégie d'extraction |
|---|---|
| NIF | Motif numérique long (10+ chiffres) à proximité des ancres `NIF`, `N.I.F` |
| STAT | Numérique à proximité de l'ancre `STAT` |
| Numéro de facture | Ancres multilingues : `Facture n°`, `FACT`, `Invoice #`, `N°`, `Faktiora` + motif alphanumérique |
| Date de facture | Motifs de dates (étape 3) ; si plusieurs dates, celle proche des ancres `Date`, `Daty` ; sinon la plus ancienne (heuristique : date facture ≤ date échéance) |
| Total HT | Montant proche des ancres `Total HT`, `Montant HT`, `Subtotal`, `Total hors taxes` |
| TVA | Montant proche de `TVA`, `VAT`, `T.V.A` (+ capture du taux `20%` si présent) |
| Total TTC | Montant proche de `Total TTC`, `Net à payer`, `Total`, `Amount due`, `Totaly` — en cas de candidats multiples : le plus grand montant de la moitié basse de la page |
| Devise | `Ar`, `Ariary`, `MGA`, `€`, `EUR`, `$`, `USD` — défaut MGA |
| Lignes d'articles | Reconstruction tabulaire par alignement vertical des blocs OCR (colonnes désignation/quantité/PU/montant) |

Les ancres exploitent les **coordonnées OCR** : un montant est associé à une ancre si leurs boîtes sont alignées horizontalement (même ligne visuelle) — beaucoup plus fiable que la proximité dans le texte linéarisé.

### 4b. Entités par NER (spaCy)

- **Nom du fournisseur** : modèle `fr_core_news_md` (entités ORG) + heuristique de zone (tiers supérieur de la page, taille de bloc) + rapprochement flou (RapidFuzz, seuil 90) avec la table `suppliers` existante — le rapprochement avec un fournisseur connu est l'extraction la plus fiable.
- **Adresse** : motifs postaux + entités LOC.
- Pipeline spaCy encapsulé dans l'adaptateur `SpacyExtractorAdapter` ; un modèle multilingue (`xx_ent_wiki_sm`) est utilisé quand la langue détectée n'est pas le français.

### 4c. Étape 5 — Contrôles de cohérence

- **HT + TVA = TTC** (tolérance 1 unité monétaire d'arrondi). Si incohérent : tentative de re-résolution (le système teste si TTC = HT × 1,20 permet d'identifier le champ mal lu et le corrige en le signalant) ; sinon `arithmetic_ok = false` → alerte visuelle pour le comptable, jamais de blocage.
- Σ lignes d'articles ≈ HT (si les lignes ont été extraites).
- Date plausible (± 2 ans autour de la date du jour).

---

## Étape 6 — Classification du type d'opération

**Problème** : classification supervisée multi-classes → `ACHAT_MARCHANDISES`, `ACHAT_SERVICES`, `ACHAT_IMMOBILISATION`, `AUTRE`.

**Features** :
- TF-IDF (uni+bigrammes, 5 000 features) sur la concaténation : désignations des lignes + nom du fournisseur ;
- features numériques : montant TTC (log), nombre de lignes, présence de mots-clés d'immobilisation (multilingues : « ordinateur/computer », « véhicule », « machine »…), historique du fournisseur (distribution de ses opérations validées).

**Modèles** (démarche expérimentale du mémoire) :
1. *Baseline* : TF-IDF + **régression logistique** (`class_weight='balanced'`) — simple, calibrée, explicable ;
2. *Avancé* : **XGBoost** sur les mêmes features ;
3. Comparaison : accuracy, F1 macro, matrice de confusion, **calibration des probabilités** (courbe de fiabilité + `CalibratedClassifierCV` si nécessaire — indispensable puisque la probabilité alimente le score de confiance).

**Amorçage (cold start)** : avant d'avoir des données annotées, la classification est assurée par un **classifieur à mots-clés** (dictionnaire multilingue par classe) qui joue le rôle de version 0.1.0 du modèle. Chaque validation du comptable produit un exemple annoté ; le premier modèle statistique est entraîné à partir de ~150 factures validées.

---

## Étape 7 — Moteur de règles + suggestion de comptes

1. Le type d'opération sélectionne la **règle active de plus haute priorité** (`accounting_rules`).
2. Le gabarit JSON génère le squelette débit/crédit : montants affectés selon `amount` (HT/VAT/TTC), comptes par défaut.
3. Pour chaque ligne `ml_refinable = true`, le **suggesteur de comptes** (second modèle ML, même architecture que le classifieur) propose le compte exact **restreint à la liste `candidates` de la règle** — le ML ne peut jamais imputer hors du cadre du PCG. Features additionnelles : compte habituel du fournisseur (`suppliers.default_account_id`), désignations des lignes.
4. Le sous-compte fournisseur est résolu par le rapprochement fournisseur (401/404 selon la règle).
5. **`BalanceValidator`** vérifie Σ débits = Σ crédits (Decimal, jamais float) — rejet ferme sinon.
6. Écriture persistée en statut `PROPOSED` avec `rule_id`, versions de modèles, confiances par ligne.

---

## Étape 8 — Score de confiance global

Formule agrégée, bornée [0,1], affichée au comptable et stockée sur l'écriture :

```
confiance = w1·C_ocr + w2·C_extraction + w3·C_classification + w4·C_comptes − P

C_ocr            = confiance moyenne OCR pondérée par les zones utilisées
C_extraction     = moyenne des confiances des champs critiques
                   (fournisseur, date, HT, TVA, TTC)
C_classification = probabilité calibrée de la classe prédite
C_comptes        = moyenne des confiances des comptes suggérés (lignes ML)
P (pénalités)    = 0,15 si arithmetic_ok = false
                 + 0,10 si fournisseur inconnu (non rapproché)
                 + 0,10 si fallback Tesseract utilisé

Poids initiaux : w1=0,25  w2=0,30  w3=0,25  w4=0,20
```

Seuils d'affichage : **≥ 0,80 vert** (vérification rapide) ; **0,50–0,80 orange** (vérification attentive) ; **< 0,50 rouge** (vérification complète recommandée). Les poids et seuils sont des paramètres de configuration ; leur ajustement empirique (corrélation entre score et taux de correction observé) constitue une expérience du mémoire.

---

## Étapes 9–10 — Boucle d'apprentissage

**Collecte** : chaque correction du comptable crée une ligne `corrections` = paire (valeur proposée, valeur retenue) + features de la facture. Une validation sans correction est aussi un signal (exemple positif).

**Réentraînement — protocole** :
- Déclenchement : manuel (Admin) ou seuil (≥ 50 nouvelles corrections non consommées) ;
- Découpage : split temporel 80/20 (les factures récentes en test — plus réaliste qu'un split aléatoire car la distribution dérive) ;
- La nouvelle version n'est **activée que si son F1 macro ≥ F1 de la version active** sur le jeu de test commun (protection anti-régression) ;
- Chaque version : artefact `.joblib` + ligne `model_versions` (algorithme, métriques, nombre d'exemples) — jamais d'écrasement, rollback possible ;
- Pas d'apprentissage en ligne : instabilité et non-auditabilité rédhibitoires en comptabilité.

**Métriques longitudinales du mémoire** (résultat expérimental central) :
- taux de propositions validées sans correction, par lot de 50 factures traitées ;
- accuracy/F1 du classifieur et du suggesteur de comptes, par version de modèle ;
- temps moyen de traitement d'une facture par le comptable (avec/sans le système).

---

## Constitution du jeu de données

- **Corpus cible** : 200–300 factures fournisseurs réelles anonymisées (ou générées de manière réaliste pour compléter), annotées manuellement : champs vérité terrain + type d'opération + imputation correcte.
- Répartition : 60 % entraînement / 20 % validation / 20 % test (split temporel), figée et versionnée pour la reproductibilité.
- Diversité contrôlée : scans propres / photos smartphone ; français / anglais ; avec / sans TVA détaillée.
