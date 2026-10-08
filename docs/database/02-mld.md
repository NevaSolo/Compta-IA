# MLD — Modèle Logique de Données (relationnel)

Notation : **PK** = clé primaire, **FK** = clé étrangère, souligné = unique.

```
users        (id, email*, password_hash, full_name, role, is_active, created_at)

suppliers    (id, name, normalized_name*, nif, stat, address,
              #default_account_id → accounts.id, created_at)

invoices     (id, #uploaded_by → users.id, #supplier_id → suppliers.id,
              original_filename, storage_path, mime_type, file_size, language,
              status, invoice_number, invoice_date, total_ht, total_vat,
              total_ttc, currency, arithmetic_ok, error_message, uploaded_at)

ocr_results  (id, #invoice_id* → invoices.id, engine, raw_text,
              mean_confidence, blocks, duration_ms, created_at)

extracted_entities (id, #invoice_id → invoices.id, entity_type, raw_value,
              normalized_value, confidence, extraction_method, source_block,
              created_at)

model_versions (id, name, version, algorithm, artifact_path, accuracy,
              f1_score, training_samples, is_active, trained_at)
              -- unicité (name, version)

classifications (id, #invoice_id* → invoices.id,
              #model_version_id → model_versions.id, operation_type,
              probability, probabilities, created_at)

accounts     (id, code*, label, account_class, parent_code, normal_balance,
              is_active, created_at)

accounting_rules (id, code*, operation_type, description, template,
              priority, is_active, created_at)

journal_entries (id, #invoice_id → invoices.id,
              #rule_id → accounting_rules.id, entry_date, label, status,
              confidence_score, #validated_by → users.id, validated_at,
              created_at)

entry_lines  (id, #entry_id → journal_entries.id [ON DELETE CASCADE],
              #account_id → accounts.id, label, debit, credit,
              account_confidence, suggested_by_ml, line_order)

corrections  (id, #entry_id → journal_entries.id,
              #entry_line_id → entry_lines.id, #corrected_by → users.id,
              field_name, original_value, corrected_value,
              used_for_training, corrected_at)

audit_logs   (id, #user_id → users.id, action, entity_type, entity_id,
              old_value, new_value, ip_address, created_at)
```

## Traduction des cardinalités du MCD

| Association MCD | Traduction relationnelle |
|---|---|
| Facture 1—1 Résultat OCR | FK `invoice_id` UNIQUE dans `ocr_results` |
| Facture 1—1 Classification | FK `invoice_id` UNIQUE dans `classifications` |
| Écriture 1—N Lignes (composition) | FK `entry_id` avec `ON DELETE CASCADE` — une ligne ne survit pas à son écriture |
| Écriture composée de 2..* lignes | Non exprimable en SQL déclaratif → invariant vérifié par la couche domaine (`BalanceValidator`) avant COMMIT |
| Fournisseur 0..1 — Facture | FK `supplier_id` NULLABLE (inconnu tant que le NLP n'a pas identifié le fournisseur) |

## Vérification de la 3NF

- **1NF** : tous les attributs sont atomiques. Les colonnes JSON (`blocks`, `template`, `probabilities`, `old_value`) stockent des *documents techniques opaques* jamais interrogés champ à champ en SQL — c'est un usage documenté et assumé, pas une violation du relationnel pour les données métier.
- **2NF** : toutes les PK sont mono-attribut (surrogate keys) → aucune dépendance partielle possible.
- **3NF** : aucune dépendance transitive — le fournisseur (nom, NIF, adresse) dépendait transitivement de la facture, il a été extrait dans `suppliers` ; l'intitulé du compte dépend du compte, pas de la ligne d'écriture ; les métriques du modèle dépendent de la version du modèle, pas de la classification.

Dénormalisation assumée et justifiée : `invoices.total_ht/total_vat/total_ttc` sont des *copies de travail* des entités extraites (accès direct sans jointure sur `extracted_entities`, qui reste la source de vérité de l'extraction avec confiance et traçabilité). Ce choix est documenté comme optimisation de lecture.
