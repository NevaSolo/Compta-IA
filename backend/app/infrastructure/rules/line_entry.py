"""Écriture ventilée ligne par ligne (étape 3 de la ventilation).

Chaque ligne de détail de la facture reçoit son propre compte, choisi parmi
les comptes autorisés par les règles du plan comptable de l'entreprise
(jamais hors plan), d'après les mots-clés de SA désignation — et non du
texte entier de la facture. Les lignes sont ensuite regroupées par règle :
chaque règle apporte son compte de TVA et son compte de tiers (une
immobilisation : TVA sur immobilisations + fournisseur d'immobilisations).

Le constructeur renvoie None quand la ventilation n'apporterait rien (toutes
les lignes vont au même compte) ou n'est pas sûre (compte absent du plan,
groupe de montant négatif…) : le pipeline garde alors l'écriture au niveau
de la facture, exactement comme avant.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core.currency import money
from app.domain.entities import EntryLine, InvoiceLine, JournalEntry
from app.domain.ports import AccountRepository
from app.domain.rules import BalanceValidator

PURCHASE_OPERATIONS = ("ACHAT_SERVICES", "ACHAT_MARCHANDISES", "ACHAT_IMMOBILISATION")
IMMOBILISATION = "ACHAT_IMMOBILISATION"

# Compléments de mots-clés propres à l'analyse d'UNE ligne (formes dérivées et
# libellés usuels absents des dictionnaires des plans). Ils ne s'appliquent qu'aux
# comptes autorisés par le plan de l'entreprise, et n'affectent pas la suggestion
# au niveau de la facture.
EXTRA_KEYWORDS: dict[str, list[str]] = {
    # plan malgache
    "613": ["salle"],
    "615": ["nettoyage", "menage"],
    "623": ["publicitaire", "campagne", "communication"],
    "625": ["frais de deplacement", "train", "avion", "voyage"],
    "626": ["affranchissement", "courrier", "postaux", "poste"],
    "628": ["abonnement", "saas", "cloud"],
    "6064": ["papeterie", "consommable", "fournitures"],
    # plan français
    "6132": ["salle de reunion", "location de salle"],
    "6155": ["nettoyage", "menage"],
    "6231": ["publicitaire", "campagne"],
    "6261": ["postaux", "poste"],
}
# Matériel professionnel (cuisine, atelier) et denrées alimentaires : mêmes
# mots-clés pour les deux plans (215 / 2154 : matériel ; 607 : marchandises).
_EQUIPMENT = ["four", "plan de travail", "chambre froide", "refrigerateur", "congelateur", "friteuse",
              "lave-vaisselle", "hotte", "piano de cuisson", "materiel de cuisine", "equipement de cuisine",
              "machine", "groupe electrogene", "compresseur", "outillage", "materiel industriel"]
_FOOD = ["denree", "alimentaire", "huile", "farine", "sucre", "riz", "lait", "beurre", "oeuf", "fromage",
         "viande", "poisson", "volaille", "poulet", "legume", "fruit", "epice", "conserve", "boisson",
         "cafe", "vin", "biere", "levure", "sel"]
_EQUIPMENT += ["plaque de cuisson", "plaques de cuisson", "cuisiniere", "four a gaz",
               # matériel médical
               "moniteur", "lit d'hospitalisation", "lit medicalise", "autoclave", "sterilisateur",
               "echographe", "defibrillateur", "electrocardiographe", "materiel medical",
               "equipement medical", "table d'examen", "fauteuil dentaire"]
# Consommables médicaux : non stockés (606), jamais immobilisés
_MEDICAL_SUPPLIES = ["serum", "compresse", "gant", "seringue", "pansement", "sterile",
                     "consommable medical", "consommables medicaux", "catheter", "masque chirurgical"]
# Petit équipement et consommables d'exploitation (vaisselle, linge, produits
# d'entretien) : une charge, par prudence, plutôt qu'une immobilisation
_SUPPLIES = ["vaisselle", "porcelaine", "couverts", "ustensile", "linge", "draps", "serviette",
             "detergent", "nettoyant", "produit d'entretien", "produits d'entretien", "savon",
             # hygiène : « papier hygiénique » n'est pas une fourniture de bureau (6064)
             "papier hygienique", "papier toilette", "essuie-tout", "mouchoir"]
# Prestations de service : installation, mise en service, formation
_SERVICES = ["installation", "mise en service", "formation"]
for _code in ("215", "2154"):
    EXTRA_KEYWORDS.setdefault(_code, []).extend(_EQUIPMENT)
EXTRA_KEYWORDS.setdefault("607", []).extend(_FOOD)
EXTRA_KEYWORDS.setdefault("606", []).extend(_SUPPLIES + _MEDICAL_SUPPLIES)     # plan malgache
EXTRA_KEYWORDS.setdefault("6063", []).extend(_SUPPLIES)    # plan français
EXTRA_KEYWORDS.setdefault("6068", []).extend(_MEDICAL_SUPPLIES)  # plan français
EXTRA_KEYWORDS.setdefault("604", []).extend(_SERVICES)
# Mots courts qui sont aussi le début d'autres mots : à reconnaître en MOT ENTIER
# (« four » ≠ « fournitures », « fournisseur » ; « sel » ≠ « sellerie » ; « riz »…)
WHOLE_WORDS = {"four", "riz", "sel", "vin", "lait", "cafe", "hotte", "fruit", "machine",
               "hotel"}  # « hôtel » (nuitée), pas « hôtelier » (lot hôtelier)
# Abonnement, location, maintenance… : une charge, jamais une immobilisation,
# même si la ligne mentionne un logiciel ou un matériel.
CHARGE_ONLY_RE = re.compile(r"\b(?:abonnement|location|loyer|maintenance|support|redevance|forfait mensuel"
                            r"|subscription|rental|lease)\b")
_WORD_CHARS = "a-z0-9"


def _normalize(text: str) -> str:
    """Minuscules sans accents : « Publicité » et « publicite » se valent."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _hits(keywords: list[str], text: str) -> int:
    """Mots-clés présents EN DÉBUT DE MOT : « eau » ne se trouve ni dans « bureau »
    ni dans « réseaux » (faux positifs d'une recherche de sous-chaîne).
    Un mot-clé de plusieurs mots compte autant que ses mots : plus précis, il l'emporte
    sur un mot seul. Cas réel : « papier hygiénique » (606) contre « papier » (6064)."""
    def pattern(kw: str) -> str:
        end = rf"s?(?![{_WORD_CHARS}])" if kw in WHOLE_WORDS else ""  # pluriel admis : « fours »
        return rf"(?<![{_WORD_CHARS}]){re.escape(kw)}{end}"
    return sum(len(kw.split()) for kw in {_normalize(k) for k in keywords} if re.search(pattern(kw), text))


@dataclass
class _Choice:
    account_code: str
    rule: dict
    confidence: float
    by_keywords: bool


@dataclass
class _Group:
    rule: dict
    charges: dict[str, Decimal]       # compte → HT
    confidences: dict[str, float]
    by_keywords: dict[str, bool]
    vat: Decimal = Decimal("0")


class LineEntryBuilder:
    def __init__(self, account_repo: AccountRepository, rules: list[dict],
                 keywords: dict[str, list[str]], fixed_asset_min_amount: Decimal = Decimal("0")):
        self.account_repo = account_repo
        self.fixed_asset_min_amount = fixed_asset_min_amount
        # Comptes autorisés → (règle propriétaire), dans l'ordre de priorité des règles
        self.candidates: dict[str, dict] = {}
        for rule in rules:
            if rule["operation_type"] not in PURCHASE_OPERATIONS:
                continue
            charge = self._charge_spec(rule)
            if charge is None:
                continue
            for code in charge.get("candidates") or [charge["default_account"]]:
                self.candidates.setdefault(code, rule)
        self.keywords = {code: list(keywords.get(code, [])) + EXTRA_KEYWORDS.get(code, [])
                         for code in self.candidates}

    # ------------------------------------------------------------------ API
    def build(self, *, lines: list[InvoiceLine], fallback_rule: dict, fallback_account: str,
              total_vat: Decimal, invoice_id: int, company_id: int, entry_date: date, label: str,
              rate: Decimal | None = None, reverse_sides: bool = False) -> JournalEntry | None:
        if not lines or self._charge_spec(fallback_rule) is None:
            return None
        choices = [self._choose(line, fallback_rule, fallback_account, rate) for line in lines]
        if len({c.account_code for c in choices}) < 2:
            return None  # un seul compte : l'écriture au niveau facture est identique

        vats = self._line_vats(lines, total_vat)
        groups: dict[str, _Group] = {}
        for line, choice, vat in zip(lines, choices, vats):
            group = groups.setdefault(choice.rule["code"], _Group(choice.rule, {}, {}, {}))
            group.charges[choice.account_code] = group.charges.get(choice.account_code, Decimal("0")) + line.amount
            group.confidences[choice.account_code] = min(group.confidences.get(choice.account_code, 1.0),
                                                         choice.confidence)
            group.by_keywords[choice.account_code] = choice.by_keywords
            group.vat += vat
        if any(amount <= 0 for g in groups.values() for amount in g.charges.values()) \
                or any(g.vat < 0 for g in groups.values()):
            return None  # remise supérieure à une charge : pas de ventilation sûre

        rule_code = fallback_rule["code"]
        entry = JournalEntry(invoice_id=invoice_id, company_id=company_id, entry_date=entry_date,
                             label=label, rule_code=rule_code)
        debits: list[tuple[str, Decimal, float | None, bool]] = []
        credits: dict[str, Decimal] = {}
        vat_lines: dict[str, Decimal] = {}
        for group in groups.values():
            vat_account = self._spec_account(group.rule, "VAT")
            tiers_account = self._spec_account(group.rule, "TTC")
            if tiers_account is None or (group.vat and vat_account is None):
                return None
            for code, amount in group.charges.items():
                debits.append((code, self._convert(amount, rate), group.confidences[code],
                               group.by_keywords[code]))
            if group.vat:
                vat_lines[vat_account] = vat_lines.get(vat_account, Decimal("0")) + group.vat
            credits[tiers_account] = credits.get(tiers_account, Decimal("0")) \
                + sum(group.charges.values()) + group.vat
        debits += [(code, self._convert(amount, rate), None, False) for code, amount in vat_lines.items()]
        credit_lines = [(code, self._convert(amount, rate)) for code, amount in credits.items()]
        # Conversion de devise : chaque montant est arrondi séparément ; l'écart
        # d'arrondi (quelques centimes) va au plus gros tiers pour rester équilibré.
        residual = sum(d[1] for d in debits) - sum(c[1] for c in credit_lines)
        if residual:
            biggest = max(range(len(credit_lines)), key=lambda i: credit_lines[i][1])
            code, amount = credit_lines[biggest]
            credit_lines[biggest] = (code, amount + residual)

        order = 0
        for code, amount, confidence, by_keywords in debits:
            entry.lines.append(self._line(code, amount, "D", label, confidence, by_keywords, order, reverse_sides))
            order += 1
        for code, amount in credit_lines:
            entry.lines.append(self._line(code, amount, "C", label, None, False, order, reverse_sides))
            order += 1
        if any(line is None for line in entry.lines):
            return None
        BalanceValidator.validate(entry)
        return entry

    # ------------------------------------------------------- Choix du compte
    def _choose(self, line: InvoiceLine, fallback_rule: dict, fallback_account: str,
                rate: Decimal | None) -> _Choice:
        text = _normalize(line.description)
        charge_only = bool(CHARGE_ONLY_RE.search(text))
        below_threshold = self.fixed_asset_min_amount > 0 and \
            abs(self._convert(line.amount, rate)) < self.fixed_asset_min_amount
        best: tuple[int, int, int] | None = None
        best_code = None
        for position, (code, rule) in enumerate(self.candidates.items()):
            is_asset = rule["operation_type"] == IMMOBILISATION
            if is_asset and (charge_only or below_threshold):
                continue
            hits = _hits(self.keywords.get(code, []), text)
            if not hits:
                continue
            # à égalité de mots-clés : une charge plutôt qu'une immobilisation (prudence),
            # puis l'ordre de priorité des règles
            key = (hits, 0 if is_asset else 1, -position)
            if best is None or key > best:
                best, best_code = key, code
        if best_code is not None:
            return _Choice(best_code, self.candidates[best_code],
                           confidence=min(0.75, 0.5 + 0.1 * best[0]), by_keywords=True)
        # Aucun indice dans la désignation : le compte retenu pour la facture entière
        rule = self.candidates.get(fallback_account, fallback_rule)
        if rule["operation_type"] == IMMOBILISATION and (charge_only or below_threshold):
            rule = fallback_rule
        return _Choice(fallback_account, rule, confidence=0.5, by_keywords=False)

    # --------------------------------------------------------------- TVA
    @staticmethod
    def _line_vats(lines: list[InvoiceLine], total_vat: Decimal) -> list[Decimal]:
        """TVA de chaque ligne : par son taux si toutes les lignes l'indiquent et
        que la somme retombe sur la TVA de la facture, sinon au prorata du HT.
        L'écart d'arrondi va à la plus grosse ligne : la somme est exacte."""
        total_ht = sum((l.amount for l in lines), Decimal("0"))
        by_rate = None
        if all(l.vat_rate is not None for l in lines):
            by_rate = [money(l.amount * l.vat_rate / 100) for l in lines]
            if abs(sum(by_rate) - total_vat) > Decimal("0.01") * max(2, len(lines)):
                by_rate = None
        if by_rate is not None:
            vats = by_rate
        elif total_ht:
            vats = [money(total_vat * l.amount / total_ht) for l in lines]
        else:
            vats = [Decimal("0")] * len(lines)
        residual = total_vat - sum(vats)
        if residual and vats:
            biggest = max(range(len(vats)), key=lambda i: abs(vats[i]))
            vats[biggest] += residual
        return vats

    # ----------------------------------------------------------- Outils
    @staticmethod
    def _charge_spec(rule: dict) -> dict | None:
        return next((spec for spec in rule["template"].get("lines", [])
                     if spec["side"] == "D" and spec["amount"] == "HT"), None)

    @staticmethod
    def _spec_account(rule: dict, amount: str) -> str | None:
        spec = next((s for s in rule["template"].get("lines", []) if s["amount"] == amount), None)
        return spec["default_account"] if spec else None

    @staticmethod
    def _convert(amount: Decimal, rate: Decimal | None) -> Decimal:
        return money(amount * rate) if rate is not None else amount

    def _line(self, code: str, amount: Decimal, side: str, label: str, confidence: float | None,
              by_keywords: bool, order: int, reverse_sides: bool) -> EntryLine | None:
        account = self.account_repo.get_by_code(code)
        if account is None or amount == 0:
            return None
        if reverse_sides:
            side = "C" if side == "D" else "D"
        return EntryLine(account_id=account.id, account_code=account.code,
                         label=f"{account.label} — {label}"[:255],
                         debit=amount if side == "D" else Decimal("0"),
                         credit=amount if side == "C" else Decimal("0"),
                         account_confidence=confidence, suggested_by_ml=by_keywords, line_order=order)
