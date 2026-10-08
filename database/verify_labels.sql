USE compta_ia_db;
SELECT code, label FROM accounts
WHERE label LIKE '%├%' OR label LIKE '%â€%' OR label REGEXP '[[:cntrl:]]'
ORDER BY code;
SELECT COUNT(*) AS total_comptes FROM accounts;
