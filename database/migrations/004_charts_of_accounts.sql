-- Plans comptables multiples : un « plan » (chart) regroupe des comptes et des
-- règles d'écriture ; chaque entreprise pointe vers le sien. Les comptes, les
-- règles et les entreprises existants passent au plan « PCG Madagascar 2005 »
-- (aucune écriture ni ligne existante n'est modifiée).
-- À appliquer une fois sur une base existante (voir README-DOCKER.md) ;
-- schema.sql l'inclut déjà.
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

ALTER TABLE accounts
  ADD COLUMN chart_id BIGINT UNSIGNED NULL AFTER id;
UPDATE accounts SET chart_id = (SELECT id FROM charts WHERE code = 'PCG_MG_2005');
ALTER TABLE accounts
  DROP INDEX uq_accounts_code,
  ADD UNIQUE KEY uq_accounts_chart_code (chart_id, code),
  ADD CONSTRAINT fk_accounts_chart FOREIGN KEY (chart_id) REFERENCES charts(id) ON DELETE RESTRICT;

ALTER TABLE accounting_rules
  ADD COLUMN chart_id BIGINT UNSIGNED NULL AFTER id;
UPDATE accounting_rules SET chart_id = (SELECT id FROM charts WHERE code = 'PCG_MG_2005');
ALTER TABLE accounting_rules
  ADD CONSTRAINT fk_rules_chart FOREIGN KEY (chart_id) REFERENCES charts(id) ON DELETE RESTRICT;

-- NULL = pas encore choisi : l'entreprise doit choisir son plan avant d'importer des factures.
ALTER TABLE companies
  ADD COLUMN chart_id BIGINT UNSIGNED NULL AFTER base_currency;
UPDATE companies SET chart_id = (SELECT id FROM charts WHERE code = 'PCG_MG_2005');
ALTER TABLE companies
  ADD CONSTRAINT fk_companies_chart FOREIGN KEY (chart_id) REFERENCES charts(id) ON DELETE RESTRICT;
