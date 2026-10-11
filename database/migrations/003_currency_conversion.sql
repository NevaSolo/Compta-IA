-- Devise de tenue de comptabilité par entreprise, taux de change, et
-- conversion des factures en devise étrangère. À appliquer une fois sur une
-- base existante (voir README-DOCKER.md) ; schema.sql l'inclut déjà.
ALTER TABLE companies
  ADD COLUMN base_currency CHAR(3) NOT NULL DEFAULT 'MGA' AFTER address;

ALTER TABLE invoices
  ADD COLUMN exchange_rate DECIMAL(18,6) NULL AFTER currency;

ALTER TABLE journal_entries
  ADD COLUMN currency          CHAR(3)       NOT NULL DEFAULT 'MGA' AFTER label,
  ADD COLUMN original_currency CHAR(3)       NULL AFTER currency,
  ADD COLUMN original_amount   DECIMAL(15,2) NULL AFTER original_currency,
  ADD COLUMN exchange_rate     DECIMAL(18,6) NULL AFTER original_amount;

CREATE TABLE exchange_rates (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  company_id     BIGINT UNSIGNED NOT NULL,
  currency       CHAR(3)         NOT NULL,
  -- 1 unité de `currency` = `rate` unités de la devise de l'entreprise
  rate           DECIMAL(18,6)   NOT NULL,
  effective_date DATE            NOT NULL,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_rate_company_currency_date (company_id, currency, effective_date),
  CONSTRAINT fk_rates_company FOREIGN KEY (company_id)
    REFERENCES companies(id) ON DELETE CASCADE,
  CONSTRAINT chk_rate_positive CHECK (rate > 0)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
