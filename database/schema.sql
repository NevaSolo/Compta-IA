-- ============================================================
-- MPD / Schéma physique MySQL 8 — compta_ia_db
-- Système intelligent de génération d'écritures comptables
-- Moteur : InnoDB — Charset : utf8mb4 — Montants : DECIMAL(15,2)
-- ============================================================

CREATE DATABASE IF NOT EXISTS compta_ia_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE compta_ia_db;

-- ------------------------------------------------------------
-- Plans comptables (un plan = des comptes + des regles d'ecriture ;
-- chaque entreprise pointe vers le sien, choix obligatoire)
-- ------------------------------------------------------------
CREATE TABLE charts (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  code        VARCHAR(30)     NOT NULL,
  name        VARCHAR(150)    NOT NULL,
  country     CHAR(2)         NULL,
  version     VARCHAR(20)     NULL,
  description VARCHAR(500)    NULL,
  is_active   TINYINT(1)      NOT NULL DEFAULT 1,
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_charts_code (code)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

INSERT INTO charts (code, name, country, version, description) VALUES
 ('PCG_MG_2005', 'Plan comptable général malgache', 'MG', '2005',
  'PCG malgache 2005 (décret n°2004-272), plan de comptes recommandé.');

-- ------------------------------------------------------------
-- 0. Entreprises (multi-tenant : une base partagée, cloisonnee
--    par company_id sur users/suppliers/invoices/journal_entries)
-- ------------------------------------------------------------
CREATE TABLE companies (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name           VARCHAR(255)    NOT NULL,
  nif            VARCHAR(50)     NULL,
  stat           VARCHAR(50)     NULL,
  address        VARCHAR(500)    NULL,
  logo_path      VARCHAR(500)    NULL,
  base_currency  CHAR(3)         NOT NULL DEFAULT 'MGA',
  -- NULL = plan comptable pas encore choisi (obligatoire avant tout import)
  chart_id       BIGINT UNSIGNED NULL,
  is_active      TINYINT(1)      NOT NULL DEFAULT 1,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_companies_chart FOREIGN KEY (chart_id)
    REFERENCES charts(id) ON DELETE RESTRICT
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 1. Utilisateurs
-- ------------------------------------------------------------
CREATE TABLE users (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  -- NULL = administrateur global de la plateforme (aucune entreprise) ;
  -- NOT NULL pour ENTREPRISE_ADMIN et COMPTABLE (compte rattache).
  company_id     BIGINT UNSIGNED NULL,
  email          VARCHAR(255)    NOT NULL,
  password_hash  VARCHAR(255)    NOT NULL,
  full_name      VARCHAR(150)    NOT NULL,
  avatar_path    VARCHAR(500)    NULL,
  theme          VARCHAR(10)     NOT NULL DEFAULT 'auto',
  accent         VARCHAR(10)     NOT NULL DEFAULT 'blue',
  role           ENUM('ADMIN','ENTREPRISE_ADMIN','COMPTABLE') NOT NULL DEFAULT 'COMPTABLE',
  is_active      TINYINT(1)      NOT NULL DEFAULT 1,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_email (email),
  KEY idx_users_company (company_id),
  CONSTRAINT fk_users_company FOREIGN KEY (company_id)
    REFERENCES companies(id) ON DELETE RESTRICT
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 2. Comptes (appartiennent a un plan comptable)
-- ------------------------------------------------------------
CREATE TABLE accounts (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  chart_id       BIGINT UNSIGNED NULL,
  code           VARCHAR(10)     NOT NULL,
  label          VARCHAR(255)    NOT NULL,
  account_class  TINYINT UNSIGNED NOT NULL,
  parent_code    VARCHAR(10)     NULL,
  normal_balance ENUM('DEBIT','CREDIT') NOT NULL,
  is_active      TINYINT(1)      NOT NULL DEFAULT 1,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounts_chart_code (chart_id, code),
  KEY idx_accounts_class (account_class),
  CONSTRAINT fk_accounts_chart FOREIGN KEY (chart_id)
    REFERENCES charts(id) ON DELETE RESTRICT,
  CONSTRAINT chk_account_class CHECK (account_class BETWEEN 1 AND 7)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 3. Fournisseurs
-- ------------------------------------------------------------
CREATE TABLE suppliers (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  company_id         BIGINT UNSIGNED NOT NULL,
  name               VARCHAR(255)    NOT NULL,
  normalized_name    VARCHAR(255)    NOT NULL,
  nif                VARCHAR(50)     NULL,
  stat               VARCHAR(50)     NULL,
  address            VARCHAR(500)    NULL,
  default_account_id BIGINT UNSIGNED NULL,
  created_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  -- Unicite par entreprise : deux societes peuvent chacune avoir un
  -- fournisseur "TOTAL" sans collision.
  UNIQUE KEY uq_suppliers_company_normalized (company_id, normalized_name),
  KEY idx_suppliers_nif (nif),
  CONSTRAINT fk_suppliers_company FOREIGN KEY (company_id)
    REFERENCES companies(id) ON DELETE RESTRICT,
  CONSTRAINT fk_suppliers_account FOREIGN KEY (default_account_id)
    REFERENCES accounts(id) ON DELETE SET NULL
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 4. Factures
-- ------------------------------------------------------------
CREATE TABLE invoices (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  company_id        BIGINT UNSIGNED NOT NULL,
  uploaded_by       BIGINT UNSIGNED NOT NULL,
  supplier_id       BIGINT UNSIGNED NULL,
  original_filename VARCHAR(255)    NOT NULL,
  storage_path      VARCHAR(500)    NOT NULL,
  mime_type         VARCHAR(100)    NOT NULL,
  file_size         INT UNSIGNED    NOT NULL,
  language          VARCHAR(10)     NULL,
  status            ENUM('UPLOADED','PREPROCESSING','OCR_DONE','ANALYZED',
                         'ENTRIES_PROPOSED','VALIDATED','REJECTED','ERROR')
                    NOT NULL DEFAULT 'UPLOADED',
  current_step      ENUM('PREPROCESSING','OCR','LANGUAGE_DETECTION',
                         'ENTITY_EXTRACTION','COHERENCE_CHECK','CLASSIFICATION',
                         'RULE_ENGINE','CONFIDENCE_SCORING','DONE') NULL,
  document_type     ENUM('FACTURE','AVOIR') NOT NULL DEFAULT 'FACTURE',
  invoice_number    VARCHAR(100)    NULL,
  invoice_date      DATE            NULL,
  total_ht          DECIMAL(15,2)   NULL,
  total_vat         DECIMAL(15,2)   NULL,
  total_ttc         DECIMAL(15,2)   NULL,
  currency          CHAR(3)         NOT NULL DEFAULT 'MGA',
  exchange_rate     DECIMAL(18,6)   NULL,
  arithmetic_ok     TINYINT(1)      NULL,
  error_message     VARCHAR(500)    NULL,
  uploaded_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_invoices_status (status),
  KEY idx_invoices_date (invoice_date),
  KEY idx_invoices_supplier (supplier_id),
  KEY idx_invoices_uploader (uploaded_by),
  KEY idx_invoices_company (company_id),
  CONSTRAINT fk_invoices_company FOREIGN KEY (company_id)
    REFERENCES companies(id) ON DELETE RESTRICT,
  CONSTRAINT fk_invoices_user FOREIGN KEY (uploaded_by)
    REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_invoices_supplier FOREIGN KEY (supplier_id)
    REFERENCES suppliers(id) ON DELETE SET NULL,
  CONSTRAINT chk_invoice_amounts CHECK (
    (total_ht IS NULL OR total_ht >= 0) AND
    (total_vat IS NULL OR total_vat >= 0) AND
    (total_ttc IS NULL OR total_ttc >= 0)
  )
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 5. Résultats OCR (1-1 avec facture)
-- ------------------------------------------------------------
CREATE TABLE ocr_results (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  invoice_id      BIGINT UNSIGNED NOT NULL,
  engine          ENUM('EASYOCR','TESSERACT','PDF_TEXT') NOT NULL,
  raw_text        MEDIUMTEXT      NOT NULL,
  mean_confidence DECIMAL(5,4)    NOT NULL,
  blocks          JSON            NOT NULL,
  duration_ms     INT UNSIGNED    NOT NULL,
  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ocr_invoice (invoice_id),
  CONSTRAINT fk_ocr_invoice FOREIGN KEY (invoice_id)
    REFERENCES invoices(id) ON DELETE CASCADE,
  CONSTRAINT chk_ocr_confidence CHECK (mean_confidence BETWEEN 0 AND 1)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 6. Entités extraites (NLP)
-- ------------------------------------------------------------
CREATE TABLE extracted_entities (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  invoice_id        BIGINT UNSIGNED NOT NULL,
  entity_type       VARCHAR(50)     NOT NULL,
  raw_value         VARCHAR(500)    NOT NULL,
  normalized_value  VARCHAR(500)    NULL,
  confidence        DECIMAL(5,4)    NOT NULL,
  extraction_method ENUM('REGEX','NER') NOT NULL,
  source_block      JSON            NULL,
  created_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_entities_invoice (invoice_id),
  KEY idx_entities_type (entity_type),
  CONSTRAINT fk_entities_invoice FOREIGN KEY (invoice_id)
    REFERENCES invoices(id) ON DELETE CASCADE,
  CONSTRAINT chk_entity_confidence CHECK (confidence BETWEEN 0 AND 1)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 7. Versions des modèles ML
-- ------------------------------------------------------------
CREATE TABLE model_versions (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name             VARCHAR(100)    NOT NULL,
  version          VARCHAR(20)     NOT NULL,
  algorithm        VARCHAR(100)    NOT NULL,
  artifact_path    VARCHAR(500)    NOT NULL,
  accuracy         DECIMAL(5,4)    NULL,
  f1_score         DECIMAL(5,4)    NULL,
  training_samples INT UNSIGNED    NOT NULL DEFAULT 0,
  is_active        TINYINT(1)      NOT NULL DEFAULT 0,
  trained_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_model_name_version (name, version),
  KEY idx_model_active (name, is_active)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 8. Classifications (1-1 avec facture)
-- ------------------------------------------------------------
CREATE TABLE classifications (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  invoice_id       BIGINT UNSIGNED NOT NULL,
  model_version_id BIGINT UNSIGNED NOT NULL,
  operation_type   ENUM('ACHAT_MARCHANDISES','ACHAT_SERVICES',
                        'ACHAT_IMMOBILISATION','AUTRE') NOT NULL,
  probability      DECIMAL(5,4)    NOT NULL,
  probabilities    JSON            NULL,
  created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_classif_invoice (invoice_id),
  CONSTRAINT fk_classif_invoice FOREIGN KEY (invoice_id)
    REFERENCES invoices(id) ON DELETE CASCADE,
  CONSTRAINT fk_classif_model FOREIGN KEY (model_version_id)
    REFERENCES model_versions(id) ON DELETE RESTRICT,
  CONSTRAINT chk_classif_proba CHECK (probability BETWEEN 0 AND 1)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 9. Règles comptables (gabarits pilotés par les données)
-- ------------------------------------------------------------
CREATE TABLE accounting_rules (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  chart_id       BIGINT UNSIGNED NULL,
  code           VARCHAR(20)     NOT NULL,
  operation_type ENUM('ACHAT_MARCHANDISES','ACHAT_SERVICES',
                      'ACHAT_IMMOBILISATION','AUTRE') NOT NULL,
  description    VARCHAR(500)    NOT NULL,
  template       JSON            NOT NULL,
  priority       INT             NOT NULL DEFAULT 100,
  is_active      TINYINT(1)      NOT NULL DEFAULT 1,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_rules_code (code),
  KEY idx_rules_operation (operation_type, is_active, priority),
  CONSTRAINT fk_rules_chart FOREIGN KEY (chart_id)
    REFERENCES charts(id) ON DELETE RESTRICT
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 10. Écritures comptables
-- ------------------------------------------------------------
CREATE TABLE journal_entries (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  -- Denormalise depuis invoices.company_id : evite une jointure sur
  -- chaque requete de listing/export scopee par entreprise.
  company_id       BIGINT UNSIGNED NOT NULL,
  invoice_id       BIGINT UNSIGNED NOT NULL,
  rule_id          BIGINT UNSIGNED NULL,
  entry_date       DATE            NOT NULL,
  label            VARCHAR(255)    NOT NULL,
  currency          CHAR(3)         NOT NULL DEFAULT 'MGA',
  original_currency CHAR(3)         NULL,
  original_amount   DECIMAL(15,2)   NULL,
  exchange_rate     DECIMAL(18,6)   NULL,
  status           ENUM('PROPOSED','CORRECTED','VALIDATED')
                   NOT NULL DEFAULT 'PROPOSED',
  confidence_score DECIMAL(5,4)    NULL,
  validated_by     BIGINT UNSIGNED NULL,
  validated_at     DATETIME        NULL,
  created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_entries_invoice (invoice_id),
  KEY idx_entries_status (status),
  KEY idx_entries_date (entry_date),
  KEY idx_entries_company (company_id),
  CONSTRAINT fk_entries_company FOREIGN KEY (company_id)
    REFERENCES companies(id) ON DELETE RESTRICT,
  CONSTRAINT fk_entries_invoice FOREIGN KEY (invoice_id)
    REFERENCES invoices(id) ON DELETE RESTRICT,
  CONSTRAINT fk_entries_rule FOREIGN KEY (rule_id)
    REFERENCES accounting_rules(id) ON DELETE SET NULL,
  CONSTRAINT fk_entries_validator FOREIGN KEY (validated_by)
    REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT chk_validated_consistency CHECK (
    (status <> 'VALIDATED') OR
    (validated_by IS NOT NULL AND validated_at IS NOT NULL)
  )
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 11. Lignes d'écriture (partie double)
-- ------------------------------------------------------------
CREATE TABLE entry_lines (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  entry_id           BIGINT UNSIGNED NOT NULL,
  account_id         BIGINT UNSIGNED NOT NULL,
  label              VARCHAR(255)    NOT NULL,
  debit              DECIMAL(15,2)   NOT NULL DEFAULT 0.00,
  credit             DECIMAL(15,2)   NOT NULL DEFAULT 0.00,
  account_confidence DECIMAL(5,4)    NULL,
  suggested_by_ml    TINYINT(1)      NOT NULL DEFAULT 0,
  line_order         SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY idx_lines_entry (entry_id),
  KEY idx_lines_account (account_id),
  CONSTRAINT fk_lines_entry FOREIGN KEY (entry_id)
    REFERENCES journal_entries(id) ON DELETE CASCADE,
  CONSTRAINT fk_lines_account FOREIGN KEY (account_id)
    REFERENCES accounts(id) ON DELETE RESTRICT,
  -- Une ligne est soit au débit, soit au crédit, jamais les deux ni aucun
  CONSTRAINT chk_line_single_side CHECK (
    (debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)
  ),
  CONSTRAINT chk_line_positive CHECK (debit >= 0 AND credit >= 0)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 12. Corrections du comptable (feedback ML)
-- ------------------------------------------------------------
CREATE TABLE corrections (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  entry_id         BIGINT UNSIGNED NOT NULL,
  entry_line_id    BIGINT UNSIGNED NULL,
  corrected_by     BIGINT UNSIGNED NOT NULL,
  field_name       VARCHAR(50)     NOT NULL,
  original_value   VARCHAR(500)    NOT NULL,
  corrected_value  VARCHAR(500)    NOT NULL,
  used_for_training TINYINT(1)     NOT NULL DEFAULT 0,
  corrected_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_corrections_entry (entry_id),
  KEY idx_corrections_training (used_for_training),
  CONSTRAINT fk_corrections_entry FOREIGN KEY (entry_id)
    REFERENCES journal_entries(id) ON DELETE CASCADE,
  CONSTRAINT fk_corrections_line FOREIGN KEY (entry_line_id)
    REFERENCES entry_lines(id) ON DELETE SET NULL,
  CONSTRAINT fk_corrections_user FOREIGN KEY (corrected_by)
    REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- 13. Journal d'audit (append-only)
-- ------------------------------------------------------------
CREATE TABLE audit_logs (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id     BIGINT UNSIGNED NULL,
  action      VARCHAR(100)    NOT NULL,
  entity_type VARCHAR(50)     NOT NULL,
  entity_id   BIGINT UNSIGNED NOT NULL,
  old_value   JSON            NULL,
  new_value   JSON            NULL,
  ip_address  VARCHAR(45)     NULL,
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_audit_user (user_id),
  KEY idx_audit_entity (entity_type, entity_id),
  KEY idx_audit_date (created_at),
  CONSTRAINT fk_audit_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

-- ------------------------------------------------------------
-- Taux de change (par entreprise) : 1 unite de `currency` = `rate` unites
-- de la devise de l'entreprise (companies.base_currency)
-- ------------------------------------------------------------
CREATE TABLE exchange_rates (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  company_id     BIGINT UNSIGNED NOT NULL,
  currency       CHAR(3)         NOT NULL,
  rate           DECIMAL(18,6)   NOT NULL,
  effective_date DATE            NOT NULL,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_rate_company_currency_date (company_id, currency, effective_date),
  CONSTRAINT fk_rates_company FOREIGN KEY (company_id)
    REFERENCES companies(id) ON DELETE CASCADE,
  CONSTRAINT chk_rate_positive CHECK (rate > 0)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
