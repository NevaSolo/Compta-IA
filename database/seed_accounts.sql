-- ============================================================
-- Peuplement du plan comptable — PCG malgache 2005
-- Source : Décret n°2004-272 du 18/02/2004, Annexe I
--          "Plan de comptes recommandé" (pages 144 à 155)
-- Les subdivisions à 4 chiffres et plus sont ouvertes par
-- l'entité conformément à l'article 520-2 du PCG 2005 et sont
-- signalées par le commentaire [SUBDIVISION 520-2].
-- ============================================================

USE compta_ia_db;

INSERT INTO accounts (code, label, account_class, parent_code, normal_balance) VALUES
-- ------------------------------------------------------------
-- CLASSE 1 - COMPTES DE CAPITAUX
-- ------------------------------------------------------------
('10',  'Capital, réserves et assimilés',                      1, NULL,  'CREDIT'),
('101', 'Capital',                                             1, '10',  'CREDIT'),
('104', 'Primes liées au capital social',                      1, '10',  'CREDIT'),
('105', 'Ecart d''évaluation',                                 1, '10',  'CREDIT'),
('106', 'Réserves',                                            1, '10',  'CREDIT'),
('108', 'Compte de l''exploitant',                             1, '10',  'CREDIT'),
('11',  'Report à nouveau',                                    1, NULL,  'CREDIT'),
('12',  'Résultat de l''exercice',                             1, NULL,  'CREDIT'),
('13',  'Produits et charges différés',                        1, NULL,  'CREDIT'),
('15',  'Provisions pour charges - passifs non courants',      1, NULL,  'CREDIT'),
('16',  'Emprunts et dettes assimilés',                        1, NULL,  'CREDIT'),
('164', 'Emprunts auprès des établissements de crédit',        1, '16',  'CREDIT'),
('165', 'Dépôts et cautionnements reçus',                      1, '16',  'CREDIT'),
('167', 'Dettes sur contrat de location-financement',          1, '16',  'CREDIT'),

-- ------------------------------------------------------------
-- CLASSE 2 - COMPTES D'IMMOBILISATIONS
-- ------------------------------------------------------------
('20',  'Immobilisations incorporelles',                       2, NULL,  'DEBIT'),
('203', 'Frais de développement immobilisables',               2, '20',  'DEBIT'),
('204', 'Logiciels informatiques et assimilés',                2, '20',  'DEBIT'),
('205', 'Concessions, droits similaires, brevets, licences',   2, '20',  'DEBIT'),
('207', 'Fonds commercial',                                    2, '20',  'DEBIT'),
('208', 'Autres immobilisations incorporelles',                2, '20',  'DEBIT'),
('21',  'Immobilisations corporelles',                         2, NULL,  'DEBIT'),
('211', 'Terrains',                                            2, '21',  'DEBIT'),
('212', 'Agencements et aménagements de terrain',              2, '21',  'DEBIT'),
('213', 'Constructions',                                       2, '21',  'DEBIT'),
('215', 'Installations techniques',                            2, '21',  'DEBIT'),
('218', 'Autres immobilisations corporelles',                  2, '21',  'DEBIT'),
('2181','Matériel de transport',                               2, '218', 'DEBIT'),  -- [SUBDIVISION 520-2]
('2182','Matériel de bureau et informatique',                  2, '218', 'DEBIT'),  -- [SUBDIVISION 520-2]
('2183','Mobilier de bureau',                                  2, '218', 'DEBIT'),  -- [SUBDIVISION 520-2]
('23',  'Immobilisations en cours',                            2, NULL,  'DEBIT'),
('26',  'Participations et créances rattachées',               2, NULL,  'DEBIT'),
('27',  'Autres immobilisations financières',                  2, NULL,  'DEBIT'),
('275', 'Dépôts et cautionnements versés',                     2, '27',  'DEBIT'),
('28',  'Amortissement des immobilisations',                   2, NULL,  'CREDIT'),

-- ------------------------------------------------------------
-- CLASSE 3 - COMPTES DE STOCKS ET EN-COURS
-- ------------------------------------------------------------
('31',  'Matières premières et fournitures',                   3, NULL,  'DEBIT'),
('32',  'Autres approvisionnements',                           3, NULL,  'DEBIT'),
('321', 'Matières consommables',                               3, '32',  'DEBIT'),
('322', 'Fournitures consommables',                            3, '32',  'DEBIT'),
('326', 'Emballages',                                          3, '32',  'DEBIT'),
('35',  'Stocks de produits',                                  3, NULL,  'DEBIT'),
('37',  'Stocks de marchandises',                              3, NULL,  'DEBIT'),

-- ------------------------------------------------------------
-- CLASSE 4 - COMPTES DE TIERS
-- ------------------------------------------------------------
('40',  'Fournisseurs et comptes rattachés',                   4, NULL,  'CREDIT'),
('401', 'Fournisseurs de biens et services',                   4, '40',  'CREDIT'),
('403', 'Fournisseurs effets à payer',                         4, '40',  'CREDIT'),
('404', 'Fournisseurs d''immobilisations',                     4, '40',  'CREDIT'),
('408', 'Fournisseurs factures non parvenues',                 4, '40',  'CREDIT'),
('409', 'Fournisseurs débiteurs : avances, RRR à obtenir',     4, '40',  'DEBIT'),
('41',  'Clients et comptes rattachés',                        4, NULL,  'DEBIT'),
('411', 'Clients',                                             4, '41',  'DEBIT'),
('42',  'Personnel et comptes rattachés',                      4, NULL,  'CREDIT'),
('421', 'Personnel, rémunérations dues',                       4, '42',  'CREDIT'),
('43',  'Organismes sociaux et comptes rattachés',             4, NULL,  'CREDIT'),
('44',  'Etat, collectivités publiques, organismes internationaux', 4, NULL, 'CREDIT'),
('444', 'Etat, impôts sur les résultats',                      4, '44',  'CREDIT'),
('445', 'Etat, taxes sur le chiffre d''affaires',              4, '44',  'CREDIT'),
('4451','TVA à payer',                                         4, '445', 'CREDIT'), -- [SUBDIVISION 520-2]
('4452','Crédit de TVA',                                       4, '445', 'DEBIT'),  -- [SUBDIVISION 520-2]
('4455','TVA à régulariser',                                   4, '445', 'CREDIT'), -- [SUBDIVISION 520-2]
('4456','TVA déductible',                                      4, '445', 'DEBIT'),  -- [SUBDIVISION 520-2]
('4457','TVA collectée',                                       4, '445', 'CREDIT'), -- [SUBDIVISION 520-2]
('447', 'Autres impôts, taxes et versements assimilés',        4, '44',  'CREDIT'),
('46',  'Débiteurs divers et créditeurs divers',               4, NULL,  'DEBIT'),

-- ------------------------------------------------------------
-- CLASSE 5 - COMPTES FINANCIERS
-- ------------------------------------------------------------
('51',  'Banques, établissements financiers et assimilés',     5, NULL,  'DEBIT'),
('512', 'Banques comptes courants',                            5, '51',  'DEBIT'),
('53',  'Caisse',                                              5, NULL,  'DEBIT'),

-- ------------------------------------------------------------
-- CLASSE 6 - COMPTES DE CHARGES
-- ------------------------------------------------------------
('60',  'Achats consommés',                                    6, NULL,  'DEBIT'),
('601', 'Matières premières',                                  6, '60',  'DEBIT'),
('602', 'Autres approvisionnements',                           6, '60',  'DEBIT'),
('604', 'Achats d''études et de prestations de service',       6, '60',  'DEBIT'),
('605', 'Achats de matériels, équipements et travaux',         6, '60',  'DEBIT'),
('606', 'Achats non stockés de matières et fournitures',       6, '60',  'DEBIT'),
('6061','Fournitures non stockables (eau, énergie)',           6, '606', 'DEBIT'), -- [SUBDIVISION 520-2]
('6064','Fournitures administratives',                         6, '606', 'DEBIT'), -- [SUBDIVISION 520-2]
('607', 'Achats de marchandises',                              6, '60',  'DEBIT'),
('608', 'Frais accessoires d''achat',                          6, '60',  'DEBIT'),
('609', 'Rabais, remises, ristournes obtenus sur achats',      6, '60',  'CREDIT'),
('61',  'Services extérieurs',                                 6, NULL,  'DEBIT'),
('611', 'Sous-traitance générale',                             6, '61',  'DEBIT'),
('613', 'Locations',                                           6, '61',  'DEBIT'),
('614', 'Charges locatives et charges de copropriété',         6, '61',  'DEBIT'),
('615', 'Entretien, réparations et maintenance',               6, '61',  'DEBIT'),
('616', 'Primes d''assurances',                                6, '61',  'DEBIT'),
('617', 'Etudes et recherches',                                6, '61',  'DEBIT'),
('618', 'Documentation et divers',                             6, '61',  'DEBIT'),
('62',  'Autres services extérieurs',                          6, NULL,  'DEBIT'),
('621', 'Personnel extérieur à l''entreprise',                 6, '62',  'DEBIT'),
('622', 'Rémunérations d''intermédiaires et honoraires',       6, '62',  'DEBIT'),
('623', 'Publicité, publication, relations publiques',         6, '62',  'DEBIT'),
('624', 'Transports de biens et transport collectif du personnel', 6, '62', 'DEBIT'),
('625', 'Déplacements, missions et réceptions',                6, '62',  'DEBIT'),
('626', 'Frais postaux et de télécommunications',              6, '62',  'DEBIT'),
('627', 'Services bancaires et assimilés',                     6, '62',  'DEBIT'),
('628', 'Cotisations et divers',                               6, '62',  'DEBIT'),
('63',  'Impôts, taxes et versements assimilés',               6, NULL,  'DEBIT'),
('64',  'Charges de personnel',                                6, NULL,  'DEBIT'),
('641', 'Rémunérations du personnel',                          6, '64',  'DEBIT'),
('645', 'Cotisations aux organismes sociaux',                  6, '64',  'DEBIT'),
('65',  'Autres charges des activités ordinaires',             6, NULL,  'DEBIT'),
('66',  'Charges financières',                                 6, NULL,  'DEBIT'),
('661', 'Charges d''intérêts',                                 6, '66',  'DEBIT'),
('68',  'Dotations aux amortissements, provisions, pertes de valeur', 6, NULL, 'DEBIT'),

-- ------------------------------------------------------------
-- CLASSE 7 - COMPTES DE PRODUITS
-- ------------------------------------------------------------
('70',  'Ventes de produits fabriqués, marchandises, prestations', 7, NULL, 'CREDIT'),
('701', 'Ventes de produits finis',                            7, '70',  'CREDIT'),
('706', 'Vente de prestations de service',                     7, '70',  'CREDIT'),
('707', 'Ventes de marchandises',                              7, '70',  'CREDIT'),
('74',  'Subventions d''exploitation',                         7, NULL,  'CREDIT'),
('75',  'Autres produits opérationnels',                       7, NULL,  'CREDIT'),
('76',  'Produits financiers',                                 7, NULL,  'CREDIT'),
('78',  'Reprises sur provisions et pertes de valeur',         7, NULL,  'CREDIT');

-- ============================================================
-- Règles comptables initiales (moteur de règles)
-- Gabarits pour factures FOURNISSEURS (achats), TVA 20 %.
-- Rôles des lignes : amount = HT | VAT | TTC
-- ============================================================

INSERT INTO accounting_rules (code, operation_type, description, template, priority) VALUES
('R-ACHAT-MARCH-01', 'ACHAT_MARCHANDISES',
 'Achat de marchandises destinées à la revente : débit 607 (HT) + 4456 (TVA), crédit 401 (TTC)',
 JSON_OBJECT('lines', JSON_ARRAY(
   JSON_OBJECT('role','charge','side','D','amount','HT','default_account','607','ml_refinable', TRUE),
   JSON_OBJECT('role','tva','side','D','amount','VAT','default_account','4456','ml_refinable', FALSE),
   JSON_OBJECT('role','tiers','side','C','amount','TTC','default_account','401','ml_refinable', FALSE)
 )), 100),

('R-ACHAT-SVC-01', 'ACHAT_SERVICES',
 'Achat de prestations de services : débit 604/61x/62x (HT) + 4456 (TVA), crédit 401 (TTC)',
 JSON_OBJECT('lines', JSON_ARRAY(
   JSON_OBJECT('role','charge','side','D','amount','HT','default_account','604','ml_refinable', TRUE,
               'candidates', JSON_ARRAY('604','611','613','615','616','617','621','622','623','624','625','626','627','628')),
   JSON_OBJECT('role','tva','side','D','amount','VAT','default_account','4456','ml_refinable', FALSE),
   JSON_OBJECT('role','tiers','side','C','amount','TTC','default_account','401','ml_refinable', FALSE)
 )), 100),

('R-ACHAT-FOURN-01', 'ACHAT_SERVICES',
 'Achat de fournitures non stockées (eau, énergie, fournitures administratives) : débit 606x (HT) + 4456, crédit 401',
 JSON_OBJECT('lines', JSON_ARRAY(
   JSON_OBJECT('role','charge','side','D','amount','HT','default_account','606','ml_refinable', TRUE,
               'candidates', JSON_ARRAY('6061','6064','606')),
   JSON_OBJECT('role','tva','side','D','amount','VAT','default_account','4456','ml_refinable', FALSE),
   JSON_OBJECT('role','tiers','side','C','amount','TTC','default_account','401','ml_refinable', FALSE)
 )), 110),

('R-ACHAT-IMMO-01', 'ACHAT_IMMOBILISATION',
 'Acquisition d''immobilisation : débit 20x/21x (HT) + 4456 (TVA), crédit 404 Fournisseurs d''immobilisations (TTC)',
 JSON_OBJECT('lines', JSON_ARRAY(
   JSON_OBJECT('role','immobilisation','side','D','amount','HT','default_account','218','ml_refinable', TRUE,
               'candidates', JSON_ARRAY('204','205','213','215','218','2181','2182','2183')),
   JSON_OBJECT('role','tva','side','D','amount','VAT','default_account','4456','ml_refinable', FALSE),
   JSON_OBJECT('role','tiers','side','C','amount','TTC','default_account','404','ml_refinable', FALSE)
 )), 100);

-- Rattache comptes et regles ci-dessus au plan malgache (cree par schema.sql)
UPDATE accounts SET chart_id = (SELECT id FROM charts WHERE code = 'PCG_MG_2005') WHERE chart_id IS NULL;
UPDATE accounting_rules SET chart_id = (SELECT id FROM charts WHERE code = 'PCG_MG_2005') WHERE chart_id IS NULL;
