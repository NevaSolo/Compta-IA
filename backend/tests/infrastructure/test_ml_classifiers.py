"""Tests du classifieur d'amorçage (mots-clés) et du suggesteur de comptes
contraint."""
from app.domain.entities import OperationType, Supplier
from app.infrastructure.ml.classifiers import (
    ConstrainedAccountSuggester, KeywordClassifier,
)


class TestKeywordClassifier:
    def setup_method(self):
        self.clf = KeywordClassifier()

    def test_classifies_immobilisation(self):
        result = self.clf.classify("Achat d'un ordinateur portable", "Fournisseur X", 1_500_000)
        assert result.operation_type == OperationType.ACHAT_IMMOBILISATION
        assert result.model_version == "keyword-0.1.0"

    def test_classifies_services(self):
        result = self.clf.classify("Facture d'électricité JIRAMA", "JIRAMA", 45_000)
        assert result.operation_type == OperationType.ACHAT_SERVICES

    def test_classifies_marchandises(self):
        result = self.clf.classify("Vente de sacs de riz vary", "Grossiste Y", 300_000)
        assert result.operation_type == OperationType.ACHAT_MARCHANDISES

    def test_no_keywords_returns_autre_with_low_confidence(self):
        result = self.clf.classify("xyz abc qwerty", None, None)
        assert result.operation_type == OperationType.AUTRE
        assert result.probability <= 0.5

    def test_probability_never_exceeds_cap(self):
        result = self.clf.classify("ordinateur ordinateur ordinateur ordinateur", "x", 1)
        assert result.probability <= 0.85

    def test_generic_invoice_table_vocabulary_does_not_bias_toward_marchandises(self):
        """Bug réel corrigé : « article », « unité », « qté » sont des en-têtes
        de tableau présents sur QUASIMENT TOUTE facture (Code article,
        Désignation, Unité de vente, Qté). Une facture de maintenance ou
        d'achat d'équipement contenant ce vocabulaire générique + un seul
        mot-clé métier ne doit plus basculer vers ACHAT_MARCHANDISES."""
        service_invoice = ("Code article Designation Unite Qte PU HT Total HT "
                           "SVC01 Maintenance informatique unite 1 300000 300000")
        result = self.clf.classify(service_invoice, "TechSupport SARL", 300_000)
        assert result.operation_type == OperationType.ACHAT_SERVICES

        immo_invoice = ("Code article Designation Unite Qte PU HT Total HT "
                        "IMM01 Ordinateur portable unite 1 2000000 2000000")
        result2 = self.clf.classify(immo_invoice, "InfoTech", 2_000_000)
        assert result2.operation_type == OperationType.ACHAT_IMMOBILISATION

    def test_genuine_goods_invoice_still_classified_correctly(self):
        """Non-régression : une vraie facture de marchandises (négoce de riz)
        reste bien classée ACHAT_MARCHANDISES après le retrait des mots-clés
        génériques."""
        goods_invoice = ("Code article Designation Unite Qte PU HT Total HT "
                         "G01 Sac de riz 50kg unite 10 50000 500000")
        result = self.clf.classify(goods_invoice, "Grossiste Riz Tana", 500_000)
        assert result.operation_type == OperationType.ACHAT_MARCHANDISES


class TestConstrainedAccountSuggester:
    def test_uses_supplier_history_when_candidate_matches(self):
        suggester = ConstrainedAccountSuggester(account_code_by_id={7: "622"})
        supplier = Supplier(id=1, company_id=1, name="Cabinet Conseil",
                           normalized_name="CABINET CONSEIL", default_account_id=7)
        suggestion = suggester.suggest("prestation de conseil", supplier,
                                       candidates=["604", "622"], default="604")
        assert suggestion.account_code == "622"
        assert suggestion.confidence == 0.90

    def test_falls_back_to_keywords_when_no_supplier_history(self):
        suggester = ConstrainedAccountSuggester()
        suggestion = suggester.suggest("facture honoraires avocat", None,
                                       candidates=["604", "622"], default="604")
        assert suggestion.account_code == "622"

    def test_falls_back_to_default_when_nothing_matches(self):
        suggester = ConstrainedAccountSuggester()
        suggestion = suggester.suggest("texte sans indice particulier", None,
                                       candidates=["604", "622"], default="604")
        assert suggestion.account_code == "604"
        assert suggestion.suggested_by_ml is False

    def test_never_returns_code_outside_candidates(self):
        suggester = ConstrainedAccountSuggester(account_code_by_id={7: "2182"})
        supplier = Supplier(id=1, company_id=1, name="X", normalized_name="X", default_account_id=7)
        # Le compte habituel du fournisseur (2182) n'est PAS dans les candidats de la règle
        suggestion = suggester.suggest("achat", supplier, candidates=["607"], default="607")
        assert suggestion.account_code == "607"


class TestContactLinesAreIgnoredForAccountSuggestion:
    """« Téléphone : 034 … » dans l'en-tête du vendeur orientait toute facture vers le compte
    de télécommunications (626), quelle que soit la nature de l'achat."""

    CANDIDATES = ["604", "626"]

    def setup_method(self):
        self.suggester = ConstrainedAccountSuggester()

    def test_vendor_phone_label_does_not_pick_the_telecom_account(self):
        text = "Vendeur : Boutique Fil\nTéléphone : 034 12 345 67\nPelote de laine acrylique\nTotal 125 000"
        assert self.suggester.suggest(text, None, self.CANDIDATES, "604").account_code == "604"

    def test_a_real_telecom_invoice_still_picks_it(self):
        text = "Abonnement internet et téléphone mobile - forfait mensuel\nTotal 45 000"
        assert self.suggester.suggest(text, None, self.CANDIDATES, "604").account_code == "626"

    def test_email_and_fax_labels_are_ignored_too(self):
        text = "E-mail : contact@x.mg\nFax : 020 22 000 00\nPrestation de conseil"
        assert self.suggester.suggest(text, None, self.CANDIDATES, "604").account_code == "604"
