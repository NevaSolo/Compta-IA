"""Plan comptable général français (PCG, règlement ANC n° 2014-03) — plan de
comptes de base : classes 1 à 7, comptes à 2, 3 ou 4 chiffres, plus les
subdivisions de TVA (44562, 44566, 44571) indispensables aux écritures d'achat.

Format : « code | libellé | sens normal (D = débit, C = crédit) ». La classe
vient du premier chiffre ; le compte parent est le plus long préfixe existant.
Les écritures générées restent des PROPOSITIONS : le comptable valide ou corrige."""

CODE = "PCG_FR_2014"
NAME = "Plan comptable général français"
COUNTRY = "FR"
VERSION = "2014"
DESCRIPTION = ("PCG français (règlement ANC 2014-03), plan de base. TVA déductible : 44566 "
               "(biens et services) et 44562 (immobilisations).")

_ACCOUNTS = """
10|Capital et réserves|C
101|Capital|C
104|Primes liées au capital social|C
105|Écarts de réévaluation|C
106|Réserves|C
1061|Réserve légale|C
1063|Réserves statutaires ou contractuelles|C
1064|Réserves réglementées|C
1068|Autres réserves|C
108|Compte de l'exploitant|C
11|Report à nouveau|C
110|Report à nouveau (solde créditeur)|C
119|Report à nouveau (solde débiteur)|D
12|Résultat de l'exercice|C
120|Résultat de l'exercice (bénéfice)|C
129|Résultat de l'exercice (perte)|D
13|Subventions d'investissement|C
14|Provisions réglementées|C
15|Provisions|C
151|Provisions pour risques|C
153|Provisions pour pensions et obligations similaires|C
155|Provisions pour impôts|C
158|Autres provisions pour charges|C
16|Emprunts et dettes assimilées|C
164|Emprunts auprès des établissements de crédit|C
165|Dépôts et cautionnements reçus|C
167|Emprunts et dettes assortis de conditions particulières|C
168|Autres emprunts et dettes assimilées|C
17|Dettes rattachées à des participations|C
18|Comptes de liaison des établissements et sociétés en participation|C
20|Immobilisations incorporelles|D
201|Frais d'établissement|D
203|Frais de recherche et de développement|D
205|Concessions et droits similaires, brevets, licences, marques, logiciels|D
206|Droit au bail|D
207|Fonds commercial|D
208|Autres immobilisations incorporelles|D
21|Immobilisations corporelles|D
211|Terrains|D
212|Agencements et aménagements de terrains|D
213|Constructions|D
214|Constructions sur sol d'autrui|D
215|Installations techniques, matériel et outillage industriels|D
2154|Matériel industriel|D
2155|Outillage industriel|D
218|Autres immobilisations corporelles|D
2181|Installations générales, agencements et aménagements divers|D
2182|Matériel de transport|D
2183|Matériel de bureau et matériel informatique|D
2184|Mobilier|D
23|Immobilisations en cours|D
231|Immobilisations corporelles en cours|D
232|Immobilisations incorporelles en cours|D
238|Avances et acomptes versés sur commandes d'immobilisations|D
26|Participations et créances rattachées à des participations|D
261|Titres de participation|D
27|Autres immobilisations financières|D
271|Titres immobilisés (droit de propriété)|D
274|Prêts|D
275|Dépôts et cautionnements versés|D
28|Amortissements des immobilisations|C
280|Amortissements des immobilisations incorporelles|C
281|Amortissements des immobilisations corporelles|C
2813|Amortissements des constructions|C
28154|Amortissements du matériel industriel|C
28182|Amortissements du matériel de transport|C
28183|Amortissements du matériel de bureau et matériel informatique|C
28184|Amortissements du mobilier|C
29|Dépréciations des immobilisations|C
31|Matières premières (et fournitures)|D
32|Autres approvisionnements|D
33|En-cours de production de biens|D
34|En-cours de production de services|D
35|Stocks de produits|D
37|Stocks de marchandises|D
39|Dépréciations des stocks et en-cours|C
40|Fournisseurs et comptes rattachés|C
401|Fournisseurs|C
4011|Fournisseurs - Achats de biens ou de prestations de services|C
4017|Fournisseurs - Retenues de garantie|C
403|Fournisseurs - Effets à payer|C
404|Fournisseurs d'immobilisations|C
405|Fournisseurs d'immobilisations - Effets à payer|C
408|Fournisseurs - Factures non parvenues|C
409|Fournisseurs débiteurs|D
4091|Fournisseurs - Avances et acomptes versés sur commandes|D
4097|Fournisseurs - Autres avoirs|D
4098|Rabais, remises, ristournes à obtenir - Avoirs non parvenus|D
41|Clients et comptes rattachés|D
411|Clients|D
413|Clients - Effets à recevoir|D
416|Clients douteux ou litigieux|D
418|Clients - Produits non encore facturés|D
419|Clients créditeurs|C
4191|Clients - Avances et acomptes reçus sur commandes|C
42|Personnel et comptes rattachés|C
421|Personnel - Rémunérations dues|C
425|Personnel - Avances et acomptes|D
428|Personnel - Charges à payer et produits à recevoir|C
43|Sécurité sociale et autres organismes sociaux|C
431|Sécurité sociale|C
437|Autres organismes sociaux|C
438|Organismes sociaux - Charges à payer et produits à recevoir|C
44|État et autres collectivités publiques|C
441|État - Subventions à recevoir|D
444|État - Impôts sur les bénéfices|C
445|État - Taxes sur le chiffre d'affaires|C
4452|TVA due intracommunautaire|C
4456|Taxes sur le chiffre d'affaires déductibles|D
44562|TVA déductible sur immobilisations|D
44566|TVA déductible sur autres biens et services|D
44567|Crédit de TVA à reporter|D
4457|Taxes sur le chiffre d'affaires collectées par l'entreprise|C
44571|TVA collectée|C
4458|Taxes sur le chiffre d'affaires à régulariser ou en attente|C
447|Autres impôts, taxes et versements assimilés|C
448|État - Charges à payer et produits à recevoir|C
45|Groupe et associés|C
455|Associés - Comptes courants|C
457|Associés - Dividendes à payer|C
46|Débiteurs divers et créditeurs divers|D
462|Créances sur cessions d'immobilisations|D
464|Dettes sur acquisitions de valeurs mobilières de placement|C
467|Autres comptes débiteurs ou créditeurs|D
468|Divers - Charges à payer et produits à recevoir|D
47|Comptes transitoires ou d'attente|D
471|Recettes à classer ou à régulariser|C
472|Dépenses à classer ou à régulariser|D
476|Différence de conversion - Actif|D
477|Différences de conversion - Passif|C
478|Autres comptes transitoires|D
48|Comptes de régularisation|D
481|Charges à répartir sur plusieurs exercices|D
486|Charges constatées d'avance|D
487|Produits constatés d'avance|C
49|Dépréciations des comptes de tiers|C
491|Dépréciations des comptes de clients|C
50|Valeurs mobilières de placement|D
51|Banques, établissements financiers et assimilés|D
511|Valeurs à l'encaissement|D
512|Banques|D
514|Chèques postaux|D
517|Autres organismes financiers|D
518|Intérêts courus|D
519|Concours bancaires courants|C
53|Caisse|D
531|Caisse|D
54|Régies d'avance et accréditifs|D
58|Virements internes|D
59|Dépréciations des comptes financiers|C
60|Achats (sauf 603)|D
601|Achats stockés - Matières premières (et fournitures)|D
602|Achats stockés - Autres approvisionnements|D
603|Variations des stocks (approvisionnements et marchandises)|D
604|Achats d'études et prestations de services|D
605|Achats de matériel, équipements et travaux|D
606|Achats non stockés de matière et fournitures|D
6061|Fournitures non stockables (eau, énergie, gaz, électricité)|D
6063|Fournitures d'entretien et de petit équipement|D
6064|Fournitures administratives|D
6068|Autres matières et fournitures|D
607|Achats de marchandises|D
609|Rabais, remises et ristournes obtenus sur achats|C
61|Services extérieurs|D
611|Sous-traitance générale|D
612|Redevances de crédit-bail|D
613|Locations|D
6132|Locations immobilières|D
6135|Locations mobilières|D
614|Charges locatives et de copropriété|D
615|Entretien et réparations|D
6152|Entretien et réparations sur biens immobiliers|D
6155|Entretien et réparations sur biens mobiliers|D
6156|Maintenance|D
616|Primes d'assurances|D
6161|Assurances multirisques|D
6163|Assurance transport|D
6168|Autres assurances|D
617|Études et recherches|D
618|Divers (services extérieurs)|D
6181|Documentation générale|D
6183|Documentation technique|D
6185|Frais de colloques, séminaires, conférences|D
62|Autres services extérieurs|D
621|Personnel extérieur à l'entreprise|D
622|Rémunérations d'intermédiaires et honoraires|D
6221|Commissions et courtages sur achats|D
6222|Commissions et courtages sur ventes|D
6226|Honoraires|D
6227|Frais d'actes et de contentieux|D
6228|Divers (rémunérations d'intermédiaires)|D
623|Publicité, publications, relations publiques|D
6231|Annonces et insertions|D
6233|Foires et expositions|D
6234|Cadeaux à la clientèle|D
6236|Catalogues et imprimés|D
6237|Publications|D
624|Transports de biens et transports collectifs du personnel|D
6241|Transports sur achats|D
6242|Transports sur ventes|D
6247|Transports collectifs du personnel|D
625|Déplacements, missions et réceptions|D
6251|Voyages et déplacements|D
6256|Missions|D
6257|Réceptions|D
626|Frais postaux et frais de télécommunications|D
6261|Frais postaux|D
6262|Frais de télécommunications|D
627|Services bancaires et assimilés|D
6271|Frais sur titres (achat, vente, garde)|D
6275|Frais sur effets|D
628|Divers (autres services extérieurs)|D
6281|Concours divers (cotisations)|D
6284|Frais de recrutement de personnel|D
63|Impôts, taxes et versements assimilés|D
631|Impôts, taxes et versements sur rémunérations (administrations des impôts)|D
633|Impôts, taxes et versements sur rémunérations (autres organismes)|D
635|Autres impôts, taxes et versements assimilés (administrations des impôts)|D
637|Autres impôts, taxes et versements assimilés (autres organismes)|D
64|Charges de personnel|D
641|Rémunérations du personnel|D
645|Charges de sécurité sociale et de prévoyance|D
647|Autres charges sociales|D
648|Autres charges de personnel|D
65|Autres charges de gestion courante|D
651|Redevances pour concessions, brevets, licences, marques, procédés, logiciels|D
654|Pertes sur créances irrécouvrables|D
658|Charges diverses de gestion courante|D
66|Charges financières|D
661|Charges d'intérêts|D
665|Escomptes accordés|D
666|Pertes de change|D
668|Autres charges financières|D
67|Charges exceptionnelles|D
671|Charges exceptionnelles sur opérations de gestion|D
675|Valeurs comptables des éléments d'actif cédés|D
678|Autres charges exceptionnelles|D
68|Dotations aux amortissements, dépréciations et provisions|D
681|Dotations aux amortissements, dépréciations et provisions - Charges d'exploitation|D
686|Dotations aux amortissements, dépréciations et provisions - Charges financières|D
687|Dotations aux amortissements, dépréciations et provisions - Charges exceptionnelles|D
69|Participation des salariés - Impôts sur les bénéfices et assimilés|D
695|Impôts sur les bénéfices|D
70|Ventes de produits fabriqués, prestations de services, marchandises|C
701|Ventes de produits finis|C
706|Prestations de services|C
707|Ventes de marchandises|C
708|Produits des activités annexes|C
709|Rabais, remises et ristournes accordés par l'entreprise|D
71|Production stockée (ou déstockage)|C
72|Production immobilisée|C
74|Subventions d'exploitation|C
75|Autres produits de gestion courante|C
758|Produits divers de gestion courante|C
76|Produits financiers|C
765|Escomptes obtenus|C
766|Gains de change|C
768|Autres produits financiers|C
77|Produits exceptionnels|C
771|Produits exceptionnels sur opérations de gestion|C
775|Produits des cessions d'éléments d'actif|C
778|Autres produits exceptionnels|C
78|Reprises sur amortissements, dépréciations et provisions|C
79|Transferts de charges|C
791|Transferts de charges d'exploitation|C
"""

# Comptes autorisés pour une charge de services (le suggesteur choisit parmi eux)
_SERVICE_CANDIDATES = [
    "604", "611", "612", "6132", "6135", "614", "6155", "6156", "6161", "617", "6181", "6185",
    "6226", "6227", "6231", "6236", "6241", "6251", "6256", "6257", "6261", "6262", "627", "6281",
    "6061", "6063", "6064", "6068",
]


def _line(role: str, side: str, amount: str, account: str, refinable: bool = False,
          candidates: list[str] | None = None) -> dict:
    line = {"role": role, "side": side, "amount": amount, "default_account": account,
            "ml_refinable": refinable}
    if candidates:
        line["candidates"] = candidates
    return line


RULES = [
    {"code": "R-FR-ACHAT-MARCH-01", "operation_type": "ACHAT_MARCHANDISES", "priority": 100,
     "description": "Achat de marchandises : débit 607 (HT) + 44566 (TVA), crédit 401 (TTC)",
     "template": {"lines": [_line("charge", "D", "HT", "607", True),
                            _line("tva", "D", "VAT", "44566"),
                            _line("tiers", "C", "TTC", "401")]}},
    {"code": "R-FR-ACHAT-SVC-01", "operation_type": "ACHAT_SERVICES", "priority": 100,
     "description": "Achat de prestations et fournitures : débit 6xx (HT) + 44566 (TVA), crédit 401 (TTC)",
     "template": {"lines": [_line("charge", "D", "HT", "604", True, _SERVICE_CANDIDATES),
                            _line("tva", "D", "VAT", "44566"),
                            _line("tiers", "C", "TTC", "401")]}},
    {"code": "R-FR-ACHAT-IMMO-01", "operation_type": "ACHAT_IMMOBILISATION", "priority": 100,
     "description": "Acquisition d'immobilisation : débit 20x/21x (HT) + 44562 (TVA), crédit 404 (TTC)",
     "template": {"lines": [_line("immobilisation", "D", "HT", "2183", True,
                                  ["205", "2154", "2155", "2181", "2182", "2183", "2184"]),
                            _line("tva", "D", "VAT", "44562"),
                            _line("tiers", "C", "TTC", "404")]}},
]


def accounts() -> list[dict]:
    """Comptes du plan : [{code, label, account_class, parent_code, normal_balance}]."""
    parsed = []
    for raw in _ACCOUNTS.strip().splitlines():
        code, label, side = (part.strip() for part in raw.split("|"))
        parsed.append((code, label, side))
    codes = {code for code, _, _ in parsed}
    result = []
    for code, label, side in parsed:
        parent = next((code[:n] for n in range(len(code) - 1, 1, -1) if code[:n] in codes), None)
        result.append({"code": code, "label": label, "account_class": int(code[0]),
                       "parent_code": parent,
                       "normal_balance": "DEBIT" if side == "D" else "CREDIT"})
    return result


# Mots-clés → compte précis (affinage de la suggestion parmi les candidats de la règle).
# Propres à ce plan : « 2182 » désigne ici le matériel de transport, pas l'informatique.
ACCOUNT_KEYWORDS: dict[str, list[str]] = {
    "6061": ["eau", "electricite", "électricité", "energie", "énergie", "gaz", "edf", "engie"],
    "6063": ["produits d'entretien", "petit équipement", "petit matériel", "petit outillage"],
    "6064": ["papier", "stylo", "fourniture", "cartouche", "toner", "enveloppe", "classeur"],
    "611":  ["sous-traitance", "sous-traitant", "subcontract"],
    "612":  ["crédit-bail", "credit-bail", "leasing"],
    "6132": ["loyer", "bail", "location de bureau", "location de local", "location immobilière"],
    "6135": ["location de matériel", "location de véhicule", "location de voiture", "location longue durée"],
    "614":  ["charges locatives", "copropriété", "charges de copropriété"],
    "6155": ["réparation", "reparation", "entretien", "repair"],
    "6156": ["maintenance", "contrat de maintenance", "support technique"],
    "6161": ["assurance", "multirisque", "insurance", "prime d'assurance"],
    "617":  ["étude", "etude", "recherche", "study"],
    "6181": ["documentation", "abonnement", "journal", "revue"],
    "6185": ["séminaire", "seminaire", "colloque", "conférence", "formation", "training"],
    "6226": ["honoraires", "avocat", "notaire", "expert-comptable", "expert comptable", "conseil",
             "consulting", "consultant", "audit", "huissier"],
    "6227": ["frais d'actes", "greffe", "contentieux"],
    "6231": ["annonce", "insertion", "publicité", "publicite", "advertising", "marketing"],
    "6236": ["catalogue", "imprimé", "impression", "flyer", "affiche"],
    "6241": ["transport", "livraison", "fret", "delivery", "shipping", "coursier"],
    "6251": ["voyage", "déplacement", "deplacement", "billet", "train", "avion", "hôtel", "hotel",
             "péage", "carburant"],
    "6256": ["mission"],
    "6257": ["réception", "restaurant", "traiteur", "repas", "cadeau"],
    "6261": ["affranchissement", "timbre", "courrier", "colissimo", "la poste"],
    "6262": ["téléphone", "telephone", "internet", "mobile", "télécom", "telecom", "fibre",
             "orange", "sfr", "bouygues", "free"],
    "627":  ["frais bancaires", "commission bancaire", "agios", "banque"],
    "6281": ["cotisation", "adhésion", "adhesion"],
    "604":  ["prestation", "étude", "service"],
    "205":  ["logiciel", "software", "licence", "license", "saas"],
    "2154": ["machine", "outillage industriel", "équipement industriel"],
    "2182": ["véhicule", "vehicule", "voiture", "camion", "utilitaire", "moto"],
    "2183": ["ordinateur", "computer", "laptop", "serveur", "imprimante", "printer", "scanner",
             "écran", "ecran", "informatique", "smartphone"],
    "2184": ["mobilier", "bureau", "chaise", "table", "armoire", "furniture", "fauteuil"],
}


DEFINITION = {
    "code": CODE, "name": NAME, "country": COUNTRY, "version": VERSION,
    "description": DESCRIPTION, "accounts": accounts, "rules": RULES,
    "keywords": ACCOUNT_KEYWORDS,
}
