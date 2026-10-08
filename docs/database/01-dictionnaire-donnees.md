# Dictionnaire des données

Système intelligent de génération automatique des écritures comptables — MySQL 8, moteur InnoDB, charset `utf8mb4`.

Conventions :
- Clés primaires : `id BIGINT UNSIGNED AUTO_INCREMENT`
- Montants : `DECIMAL(15,2)` — jamais de FLOAT en comptabilité
- Horodatage : `DATETIME` (UTC), `created_at` systématique
- Booléens : `TINYINT(1)`

---

## 1. users — Utilisateurs du système

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| email | VARCHAR(255) UNIQUE | Non | Identifiant de connexion |
| password_hash | VARCHAR(255) | Non | Hash bcrypt du mot de passe |
| full_name | VARCHAR(150) | Non | Nom complet |
| role | ENUM('ADMIN','COMPTABLE') | Non | Rôle RBAC |
| is_active | TINYINT(1) | Non | Compte actif (désactivation sans suppression) |
| created_at | DATETIME | Non | Date de création |

## 2. suppliers — Fournisseurs (3NF : extrait de la facture)

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| name | VARCHAR(255) | Non | Raison sociale |
| normalized_name | VARCHAR(255) UNIQUE | Non | Nom normalisé (déduplication OCR) |
| nif | VARCHAR(50) | Oui | Numéro d'identification fiscale |
| stat | VARCHAR(50) | Oui | Numéro statistique (Madagascar) |
| address | VARCHAR(500) | Oui | Adresse |
| default_account_id | BIGINT UNSIGNED FK→accounts | Oui | Compte fournisseur habituel (appris des validations) |
| created_at | DATETIME | Non | Date de création |

## 3. invoices — Factures importées

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| uploaded_by | BIGINT UNSIGNED FK→users | Non | Utilisateur ayant importé |
| supplier_id | BIGINT UNSIGNED FK→suppliers | Oui | Fournisseur identifié (null tant que non extrait) |
| original_filename | VARCHAR(255) | Non | Nom du fichier d'origine |
| storage_path | VARCHAR(500) | Non | Chemin de stockage sur disque |
| mime_type | VARCHAR(100) | Non | Type MIME (pdf, jpeg, png) |
| file_size | INT UNSIGNED | Non | Taille en octets |
| language | VARCHAR(10) | Oui | Langue détectée/choisie (fr, en, ...) |
| status | ENUM(...) | Non | UPLOADED, PREPROCESSING, OCR_DONE, ANALYZED, ENTRIES_PROPOSED, VALIDATED, REJECTED, ERROR |
| invoice_number | VARCHAR(100) | Oui | Numéro de facture extrait |
| invoice_date | DATE | Oui | Date de la facture extraite |
| total_ht | DECIMAL(15,2) | Oui | Total hors taxes extrait |
| total_vat | DECIMAL(15,2) | Oui | Total TVA extrait |
| total_ttc | DECIMAL(15,2) | Oui | Total TTC extrait |
| currency | CHAR(3) | Non | Devise ISO 4217 (défaut MGA) |
| arithmetic_ok | TINYINT(1) | Oui | Contrôle HT + TVA = TTC (null = non vérifié) |
| error_message | VARCHAR(500) | Oui | Message si status = ERROR |
| uploaded_at | DATETIME | Non | Date d'import |

## 4. ocr_results — Résultats bruts de l'OCR

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| invoice_id | BIGINT UNSIGNED FK→invoices UNIQUE | Non | Facture concernée (1-1) |
| engine | ENUM('EASYOCR','TESSERACT') | Non | Moteur utilisé |
| raw_text | MEDIUMTEXT | Non | Texte brut extrait |
| mean_confidence | DECIMAL(5,4) | Non | Confiance moyenne [0,1] |
| blocks | JSON | Non | Blocs : texte, coordonnées, confiance par mot |
| duration_ms | INT UNSIGNED | Non | Durée du traitement |
| created_at | DATETIME | Non | Date du traitement |

## 5. extracted_entities — Entités extraites par le NLP

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| invoice_id | BIGINT UNSIGNED FK→invoices | Non | Facture concernée |
| entity_type | VARCHAR(50) | Non | SUPPLIER_NAME, INVOICE_NUMBER, INVOICE_DATE, TOTAL_HT, TOTAL_VAT, TOTAL_TTC, LINE_ITEM, NIF, ... |
| raw_value | VARCHAR(500) | Non | Valeur telle qu'extraite |
| normalized_value | VARCHAR(500) | Oui | Valeur normalisée (date ISO, décimal...) |
| confidence | DECIMAL(5,4) | Non | Confiance [0,1] |
| extraction_method | ENUM('REGEX','NER') | Non | Méthode d'extraction (explicabilité) |
| source_block | JSON | Oui | Zone source sur l'image (traçabilité visuelle) |
| created_at | DATETIME | Non | Date d'extraction |

## 6. model_versions — Versions des modèles ML

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| name | VARCHAR(100) | Non | Nom du modèle (operation_classifier, account_suggester) |
| version | VARCHAR(20) | Non | Version sémantique (1.0.0, 1.1.0...) |
| algorithm | VARCHAR(100) | Non | Algorithme (LogisticRegression, XGBoost...) |
| artifact_path | VARCHAR(500) | Non | Chemin du fichier .joblib |
| accuracy | DECIMAL(5,4) | Oui | Accuracy sur jeu d'évaluation |
| f1_score | DECIMAL(5,4) | Oui | F1 macro sur jeu d'évaluation |
| training_samples | INT UNSIGNED | Non | Nombre d'exemples d'entraînement |
| is_active | TINYINT(1) | Non | Version actuellement servie |
| trained_at | DATETIME | Non | Date d'entraînement |

Contrainte métier : une seule version active par `name` (index unique filtré applicativement).

## 7. classifications — Classification du type d'opération

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| invoice_id | BIGINT UNSIGNED FK→invoices UNIQUE | Non | Facture concernée (1-1) |
| model_version_id | BIGINT UNSIGNED FK→model_versions | Non | Version du modèle ayant produit la prédiction |
| operation_type | ENUM('ACHAT_MARCHANDISES','ACHAT_SERVICES','ACHAT_IMMOBILISATION','AUTRE') | Non | Classe prédite |
| probability | DECIMAL(5,4) | Non | Probabilité de la classe prédite |
| probabilities | JSON | Oui | Distribution complète des probabilités |
| created_at | DATETIME | Non | Date de prédiction |

## 8. accounts — Plan comptable (PCG malgache 2005)

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| code | VARCHAR(10) UNIQUE | Non | Numéro de compte (ex : 606100) |
| label | VARCHAR(255) | Non | Intitulé du compte |
| account_class | TINYINT UNSIGNED | Non | Classe 1 à 7 |
| parent_code | VARCHAR(10) | Oui | Compte parent (hiérarchie du plan) |
| normal_balance | ENUM('DEBIT','CREDIT') | Non | Sens normal du compte |
| is_active | TINYINT(1) | Non | Compte utilisable |
| created_at | DATETIME | Non | Date de création |

## 9. accounting_rules — Moteur de règles (gabarits d'écritures)

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| code | VARCHAR(20) UNIQUE | Non | Code de la règle (ex : R-ACHAT-SVC-01) |
| operation_type | ENUM(... même liste que classifications) | Non | Type d'opération déclencheur |
| description | VARCHAR(500) | Non | Description lisible de la règle |
| template | JSON | Non | Gabarit des lignes : [{role: 'charge', side: 'D', amount: 'HT', default_account: '606...'}, ...] |
| priority | INT | Non | Ordre d'application si plusieurs règles candidates |
| is_active | TINYINT(1) | Non | Règle active |
| created_at | DATETIME | Non | Date de création |

## 10. journal_entries — Écritures comptables

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| invoice_id | BIGINT UNSIGNED FK→invoices | Non | Facture source |
| rule_id | BIGINT UNSIGNED FK→accounting_rules | Oui | Règle appliquée (explicabilité) |
| entry_date | DATE | Non | Date comptable |
| label | VARCHAR(255) | Non | Libellé de l'écriture |
| status | ENUM('PROPOSED','CORRECTED','VALIDATED') | Non | État de l'écriture |
| confidence_score | DECIMAL(5,4) | Oui | Score de confiance global agrégé |
| validated_by | BIGINT UNSIGNED FK→users | Oui | Comptable ayant validé |
| validated_at | DATETIME | Oui | Date de validation |
| created_at | DATETIME | Non | Date de génération |

Invariant : Σ débits = Σ crédits des lignes — vérifié par la couche domaine avant persistance et re-vérifié à la validation.

## 11. entry_lines — Lignes d'écriture (partie double)

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| entry_id | BIGINT UNSIGNED FK→journal_entries | Non | Écriture parente (suppression en cascade) |
| account_id | BIGINT UNSIGNED FK→accounts | Non | Compte imputé |
| label | VARCHAR(255) | Non | Libellé de la ligne |
| debit | DECIMAL(15,2) | Non | Montant au débit (0 si crédit) |
| credit | DECIMAL(15,2) | Non | Montant au crédit (0 si débit) |
| account_confidence | DECIMAL(5,4) | Oui | Confiance du compte suggéré |
| suggested_by_ml | TINYINT(1) | Non | Compte affiné par le ML (vs règle seule) |
| line_order | SMALLINT UNSIGNED | Non | Ordre d'affichage |

Contrainte CHECK : `(debit = 0 XOR credit = 0)` et `debit >= 0 AND credit >= 0`.

## 12. corrections — Corrections du comptable (données d'apprentissage)

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| entry_id | BIGINT UNSIGNED FK→journal_entries | Non | Écriture corrigée |
| entry_line_id | BIGINT UNSIGNED FK→entry_lines | Oui | Ligne concernée (null si correction d'en-tête) |
| corrected_by | BIGINT UNSIGNED FK→users | Non | Auteur de la correction |
| field_name | VARCHAR(50) | Non | Champ corrigé (account_id, debit, credit, label...) |
| original_value | VARCHAR(500) | Non | Valeur proposée par le système |
| corrected_value | VARCHAR(500) | Non | Valeur retenue par le comptable |
| used_for_training | TINYINT(1) | Non | Déjà consommée par un réentraînement |
| corrected_at | DATETIME | Non | Date de la correction |

## 13. audit_logs — Journal d'audit

| Champ | Type | Null | Description |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | Non | Identifiant unique |
| user_id | BIGINT UNSIGNED FK→users | Oui | Auteur (null pour actions système/pipeline) |
| action | VARCHAR(100) | Non | Action (INVOICE_UPLOADED, ENTRY_VALIDATED, USER_CREATED...) |
| entity_type | VARCHAR(50) | Non | Type d'entité concernée |
| entity_id | BIGINT UNSIGNED | Non | Identifiant de l'entité |
| old_value | JSON | Oui | État avant |
| new_value | JSON | Oui | État après |
| ip_address | VARCHAR(45) | Oui | Adresse IP (IPv4/IPv6) |
| created_at | DATETIME | Non | Horodatage |

Table en append-only : aucun UPDATE/DELETE applicatif autorisé.
