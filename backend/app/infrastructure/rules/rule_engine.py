"""Moteur de règles comptables (Phase 6, étape 7).

Piloté par les données : les gabarits JSON de la table accounting_rules
génèrent le squelette débit/crédit ; le suggesteur de comptes n'affine que
les lignes ml_refinable, parmi leurs candidats. L'équilibre est vérifié par
BalanceValidator avant tout retour."""
from datetime import date
from decimal import Decimal

from app.domain.entities import EntryLine, JournalEntry, Supplier
from app.domain.ports import AccountRepository, AccountSuggester
from app.domain.rules import BalanceValidator


class RuleEngineError(Exception):
    pass


class RuleEngine:
    def __init__(self, account_repo: AccountRepository, suggester: AccountSuggester):
        self.account_repo = account_repo
        self.suggester = suggester

    def generate_entry(self, rule: dict, invoice_id: int, company_id: int,
                       entry_date: date, label: str, amounts: dict[str, Decimal],
                       invoice_text: str, supplier: Supplier | None,
                       reverse_sides: bool = False) -> JournalEntry:
        """Applique le gabarit d'une règle et retourne une écriture équilibrée.

        amounts : {'HT': Decimal, 'VAT': Decimal, 'TTC': Decimal}
        reverse_sides : une facture d'avoir (note de crédit fournisseur)
        réduit la dette envers le tiers au lieu de la créer — le sens de
        chaque ligne du gabarit (pensé pour un achat normal) doit donc être
        inversé, tout en gardant des montants positifs (cf. contrainte
        chk_invoice_amounts en base, qui interdit les montants négatifs).
        """
        template_lines = rule["template"].get("lines", [])
        if not template_lines:
            raise RuleEngineError(f"Gabarit vide pour la règle {rule['code']}")

        entry = JournalEntry(invoice_id=invoice_id, company_id=company_id,
                             entry_date=entry_date, label=label, rule_code=rule["code"])

        for order, spec in enumerate(template_lines):
            amount = amounts.get(spec["amount"])
            if amount is None:
                raise RuleEngineError(
                    f"Montant {spec['amount']} indisponible pour la règle {rule['code']}")
            if amount < 0:
                raise RuleEngineError(
                    f"Montant {spec['amount']} négatif pour la règle {rule['code']}")
            if amount == 0:
                # Une TVA à 0 est une valeur légitime (facture exonérée,
                # cf. VATCalculator.resolve_missing) : la ligne ne s'applique
                # simplement pas, elle n'est pas une donnée manquante — on
                # l'omet de l'écriture plutôt que d'échouer.
                continue

            account_code = spec["default_account"]
            confidence, by_ml = None, False
            if spec.get("ml_refinable"):
                suggestion = self.suggester.suggest(
                    text=invoice_text, supplier=supplier,
                    candidates=spec.get("candidates", [account_code]),
                    default=account_code)
                account_code = suggestion.account_code
                confidence = suggestion.confidence
                by_ml = suggestion.suggested_by_ml

            account = self.account_repo.get_by_code(account_code)
            if account is None:
                raise RuleEngineError(f"Compte {account_code} absent du plan comptable")

            side = spec["side"]
            if reverse_sides:
                side = "C" if side == "D" else "D"
            entry.lines.append(EntryLine(
                account_id=account.id, account_code=account.code,
                label=f"{account.label} — {label}"[:255],
                debit=amount if side == "D" else Decimal("0"),
                credit=amount if side == "C" else Decimal("0"),
                account_confidence=confidence, suggested_by_ml=by_ml,
                line_order=order))

        # Invariant de la partie double : premier des deux points de contrôle
        BalanceValidator.validate(entry)
        return entry
