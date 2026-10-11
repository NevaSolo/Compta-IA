-- Personnalisation du profil (photo, thème) et logo d'entreprise.
-- À appliquer une fois sur une base existante (voir README-DOCKER.md) :
-- les nouveaux déploiements l'obtiennent déjà via database/schema.sql.
ALTER TABLE users
  ADD COLUMN avatar_path VARCHAR(500) NULL AFTER full_name,
  ADD COLUMN theme       VARCHAR(10)  NOT NULL DEFAULT 'auto' AFTER avatar_path,
  ADD COLUMN accent      VARCHAR(10)  NOT NULL DEFAULT 'blue' AFTER theme;

ALTER TABLE companies
  ADD COLUMN logo_path VARCHAR(500) NULL AFTER address;
