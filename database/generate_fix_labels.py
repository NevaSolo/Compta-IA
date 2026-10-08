"""Génère un script SQL correctif pour les libellés de comptes corrompus
(mojibake constaté suite à l'exécution initiale de seed_accounts.sql via
un client dont l'encodage console différait de l'UTF-8 du fichier source).

Ce script relit le fichier source (correctement encodé en UTF-8 sur disque)
et génère des UPDATE par code de compte — aucune ressaisie manuelle,
aucun risque de réintroduire l'erreur."""
import re

with open("seed_accounts.sql", encoding="utf-8") as f:
    content = f.read()

# Le libellé peut contenir des apostrophes échappées à la façon SQL standard
# (doublées : d''évaluation) — (?:[^']|'')* les gère, contrairement au
# précédent motif qui ne traitait que l'échappement par antislash.
pattern = re.compile(
    r"\('([^']+)',\s*'((?:[^']|'')*)',\s*\d+,\s*(?:NULL|'[^']*'),\s*'(?:DEBIT|CREDIT)'\)"
)
rows = pattern.findall(content)
print(f"{len(rows)} comptes trouvés dans le fichier source")

with open("fix_account_labels_utf8.sql", "w", encoding="utf-8") as out:
    out.write("-- Correction des libellés corrompus (mojibake) du plan comptable\n")
    out.write("-- Généré automatiquement depuis seed_accounts.sql (source de vérité UTF-8)\n")
    out.write("USE compta_ia_db;\n\n")
    for code, label in rows:
        label_unescaped = label.replace("''", "'")  # dé-échapper la source SQL
        escaped = label_unescaped.replace("'", "''")  # ré-échapper pour l'UPDATE généré
        out.write(f"UPDATE accounts SET label='{escaped}' WHERE code='{code}';\n")

print("Script écrit : fix_account_labels_utf8.sql")
