-- Lignes de détail des factures (tableau articles / prestations), extraites
-- par le pipeline. Étape 1 de la ventilation ligne par ligne : consultation
-- uniquement, l'écriture reste générée au niveau de la facture.
-- À appliquer une fois sur une base existante ; schema.sql l'inclut déjà.
CREATE TABLE invoice_lines (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  invoice_id   BIGINT UNSIGNED NOT NULL,
  line_no      SMALLINT UNSIGNED NOT NULL,
  description  VARCHAR(500)    NOT NULL,
  quantity     DECIMAL(15,4)   NULL,
  unit_price   DECIMAL(15,4)   NULL,
  -- montant imprimé sur la ligne ; négatif pour une ligne de remise
  amount       DECIMAL(15,2)   NOT NULL,
  -- taux de TVA en pourcentage (20.00), si la facture l'indique par ligne
  vat_rate     DECIMAL(5,2)    NULL,
  confidence   DECIMAL(5,4)    NOT NULL,
  source_bbox  JSON            NULL,
  created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_invoice_lines_no (invoice_id, line_no),
  CONSTRAINT fk_invoice_lines_invoice FOREIGN KEY (invoice_id)
    REFERENCES invoices(id) ON DELETE CASCADE,
  CONSTRAINT chk_invoice_line_confidence CHECK (confidence BETWEEN 0 AND 1)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
