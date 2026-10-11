-- Lecture directe de la couche texte des PDF numériques (moteur "PDF_TEXT").
-- À exécuter UNE fois sur une base existante ; schema.sql contient déjà la
-- valeur pour les nouvelles installations.
--   mysql --default-character-set=utf8mb4 -u root compta_ia_db < 001_ocr_engine_pdf_text.sql
ALTER TABLE ocr_results
  MODIFY engine ENUM('EASYOCR','TESSERACT','PDF_TEXT') NOT NULL;
