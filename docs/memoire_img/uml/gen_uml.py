# -*- coding: utf-8 -*-
"""Génère les diagrammes UML du mémoire avec Graphviz (dot)."""
import html, os, subprocess

DOT = r"C:\Program Files\Graphviz\bin\dot.exe"
OUT = os.path.dirname(os.path.abspath(__file__))
FONT = "Arial"
HEAD = "#E8EEF5"; BORDER = "#2F4B6B"


def cls(name, attrs=(), methods=(), stereo=None):
    e = html.escape
    rows = []
    title = (f'<FONT POINT-SIZE="9">&laquo;{e(stereo)}&raquo;</FONT><BR/>' if stereo else "") + f"<B>{e(name)}</B>"
    rows.append(f'<TR><TD BGCOLOR="{HEAD}" CELLPADDING="4">{title}</TD></TR>')
    rows.append('<TR><TD ALIGN="LEFT" BALIGN="LEFT" CELLPADDING="3">' + ("<BR/>".join(e(a) for a in attrs) or " ") + "</TD></TR>")
    if methods is not None:
        rows.append('<TR><TD ALIGN="LEFT" BALIGN="LEFT" CELLPADDING="3">' + ("<BR/>".join(e(m) for m in methods) or " ") + "</TD></TR>")
    return f'<<TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" COLOR="{BORDER}" BGCOLOR="white">{"".join(rows)}</TABLE>>'


def render(name, body, graph_attrs=""):
    src = f'''digraph G {{
  graph [fontname="{FONT}", fontsize=12, bgcolor="white", {graph_attrs}];
  node [fontname="{FONT}", fontsize=10];
  edge [fontname="{FONT}", fontsize=9, color="#333333"];
{body}
}}'''
    path = os.path.join(OUT, name + ".dot")
    open(path, "w", encoding="utf-8").write(src)
    subprocess.run([DOT, "-Tpng", "-Gdpi=170", path, "-o", os.path.join(OUT, name + ".png")], check=True)
    print("ok", name)


def assoc(a, b, ma="", mb="", label="", kind="assoc", extra=""):
    attrs = {"assoc": 'dir=none', "compo": 'dir=back, arrowtail=diamond', "gen": 'arrowhead=empty',
             "dep": 'style=dashed, arrowhead=vee'}[kind]
    lab = f', label="{label}"' if label else ""
    mults = (f', taillabel="{ma}"' if ma else "") + (f', headlabel="{mb}"' if mb else "")
    return f'  "{a}" -> "{b}" [{attrs}{lab}{mults}, labeldistance=1.6, labelangle=30{extra}];\n'


# =========================================================== 1. cas d'utilisation
def use_case():
    b = ""
    for a in ("Utilisateur", "Comptable", "Administrateur"):
        b += f'  "{a}" [shape=none, image="{OUT}\\\\actor.png", label="{a}", labelloc=b, height=1.25, width=0.9, imagescale=true, fixedsize=true, fontsize=11];\n'
    b += '  subgraph cluster_sys { label=<<B>Système intelligent de génération des écritures comptables</B>>; style=rounded; color="#2F4B6B"; fontsize=12;\n'
    ucs = {
        "auth": "S'authentifier", "logout": "Se déconnecter", "import": "Importer une facture", "consult": "Consulter une facture",
        "suppr": "Supprimer une facture", "lancer": "Lancer le traitement\nautomatique", "pretr": "Prétraiter la facture",
        "ocr": "Extraire les informations\npar OCR", "nlp": "Analyser le contenu\npar NLP", "nature": "Identifier la nature\nde l'opération",
        "comptes": "Proposer les comptes\ncomptables", "score": "Calculer le score\nde confiance", "gen": "Générer l'écriture\ncomptable",
        "regles": "Appliquer les règles\ncomptables", "equil": "Vérifier l'équilibre\nDébit = Crédit", "prop": "Consulter la proposition",
        "modif": "Modifier l'écriture", "valid": "Valider l'écriture", "rejet": "Rejeter l'écriture",
        "hist": "Consulter l'historique", "users": "Gérer les utilisateurs", "roles": "Gérer les rôles", "retrain": "Réentraîner le modèle"}
    for k, v in ucs.items():
        b += f'    {k} [shape=ellipse, style=filled, fillcolor="#F4F6F9", color="#2F4B6B", label="{v}"];\n'
    b += "  }\n"
    # généralisation des acteurs
    b += '  "Comptable" -> "Utilisateur" [arrowhead=empty, constraint=false];\n'
    b += '  "Administrateur" -> "Utilisateur" [arrowhead=empty, constraint=false];\n'
    for k in ("auth", "logout", "import", "consult", "lancer"):
        b += f'  "Utilisateur" -> {k} [arrowhead=none];\n'
    for k in ("prop", "modif", "valid", "rejet", "hist"):
        b += f'  "Comptable" -> {k} [arrowhead=none];\n'
    for k in ("users", "roles", "hist", "retrain"):
        b += f'  "Administrateur" -> {k} [arrowhead=none];\n'
    inc = [("lancer", "pretr"), ("lancer", "ocr"), ("lancer", "nlp"), ("lancer", "nature"), ("lancer", "comptes"),
           ("lancer", "score"), ("lancer", "gen"), ("gen", "regles"), ("gen", "equil"), ("prop", "score")]
    for a, c in inc:
        b += f'  {a} -> {c} [style=dashed, arrowhead=vee, label="«include»", fontsize=8];\n'
    for a, c in [("suppr", "consult"), ("modif", "prop"), ("valid", "prop"), ("rejet", "prop")]:
        b += f'  {a} -> {c} [style=dashed, arrowhead=vee, label="«extend»", fontsize=8];\n'
    b += '  { rank=same; "Utilisateur"; "Comptable"; "Administrateur"; }\n'
    render("cas_utilisation", b, 'rankdir=LR, nodesep=0.25, ranksep=0.7, splines=true')


# =========================================================== définitions communes
C = {
 "Entreprise": (["idEntreprise", "nom", "nif", "stat", "devise"], []),
 "PlanComptable": (["idPlan", "nom", "pays"], []),
 "CompteComptable": (["numeroCompte", "libelle", "classe"], []),
 "Utilisateur": (["idUtilisateur", "nom", "email", "role"], []),
 "Facture": (["idFacture", "numeroFacture", "dateFacture", "typeFacture", "devise", "montantHT", "montantTVA", "montantTTC", "statut"], []),
 "Document": (["idDocument", "nomFichier", "typeFichier", "taille", "chemin"], []),
 "Fournisseur": (["idFournisseur", "raisonSociale", "adresse", "nif", "stat"], []),
 "Client": (["idClient", "raisonSociale", "adresse", "nif"], []),
 "TauxChange": (["idTaux", "devise", "taux", "dateEffet"], []),
 "TraitementOCR": (["idOCR", "moteur", "texteExtrait", "scoreConfiance", "dateTraitement"], []),
 "InformationExtraite": (["idInformation", "typeInformation", "valeur", "scoreConfiance"], []),
 "Analyse": (["idAnalyse", "natureOperation", "scoreConfiance"], []),
 "ModeleIA": (["idModele", "version", "algorithme", "f1Score", "actif"], []),
 "PredictionCompte": (["idPrediction", "numeroComptePropose", "scoreConfiance"], []),
 "RegleComptable": (["idRegle", "natureOperation", "comptesCandidats", "condition"], []),
 "EcritureComptable": (["idEcriture", "dateEcriture", "statut", "totalDebit", "totalCredit", "scoreConfiance"], []),
 "LigneEcriture": (["idLigne", "libelle", "montantDebit", "montantCredit"], []),
 "Validation": (["idValidation", "decision", "commentaire", "dateValidation", "validePar"], []),
 "Correction": (["idCorrection", "champ", "ancienneValeur", "nouvelleValeur", "dateCorrection", "auteur"], []),
 "Historique": (["idHistorique", "action", "description", "dateAction", "auteur"], []),
}
A = [  # (A, B, multA, multB, libellé, type)
 ("Entreprise", "Utilisateur", "1", "1..*", "emploie", "assoc"),
 ("Entreprise", "PlanComptable", "0..*", "1", "choisit", "assoc"),
 ("PlanComptable", "CompteComptable", "1", "1..*", "contient", "compo"),
 ("Entreprise", "Facture", "1", "0..*", "possède", "assoc"),
 ("Utilisateur", "Facture", "1", "0..*", "importe", "assoc"),
 ("Facture", "Document", "1", "1", "est stockée dans", "compo"),
 ("Facture", "Fournisseur", "0..*", "1", "émise par", "assoc"),
 ("Facture", "Client", "0..*", "0..1", "adressée à", "assoc"),
 ("Facture", "TauxChange", "0..*", "0..1", "convertie selon", "assoc"),
 ("Facture", "TraitementOCR", "1", "1", "subit", "assoc"),
 ("TraitementOCR", "InformationExtraite", "1", "1..*", "produit", "compo"),
 ("Facture", "Analyse", "1", "0..1", "fait l'objet de", "assoc"),
 ("Analyse", "PredictionCompte", "1", "1..*", "propose", "compo"),
 ("ModeleIA", "PredictionCompte", "1", "0..*", "produit", "assoc"),
 ("Analyse", "RegleComptable", "0..*", "1", "applique", "assoc"),
 ("RegleComptable", "CompteComptable", "0..*", "1..*", "autorise", "assoc"),
 ("PredictionCompte", "CompteComptable", "0..*", "1", "désigne", "assoc"),
 ("Facture", "EcritureComptable", "1", "0..1", "génère", "assoc"),
 ("EcritureComptable", "LigneEcriture", "1", "2..*", "contient", "compo"),
 ("LigneEcriture", "CompteComptable", "0..*", "1", "imputée sur", "assoc"),
 ("EcritureComptable", "Validation", "1", "0..1", "fait l'objet de", "assoc"),
 ("EcritureComptable", "Correction", "1", "0..*", "peut subir", "assoc"),
 ("Correction", "ModeleIA", "0..*", "0..1", "alimente", "assoc"),
 ("Facture", "Historique", "1", "0..*", "trace", "assoc"),
]


def domain():
    b = '  node [shape=plain];\n'
    for n, (at, _) in C.items():
        b += f'  "{n}" [label={cls(n, at, None)}];\n'
    for a, c, ma, mb, lab, k in A:
        b += assoc(a, c, ma, mb, lab, k)
    render("modele_domaine", b, 'rankdir=TB, nodesep=0.35, ranksep=0.55, splines=true, concentrate=false')


# =========================================================== classes de conception (typées, avec méthodes)
T = {
 "Utilisateur": (["-idUtilisateur : int", "-nom : String", "-email : String", "-motDePasse : String", "-actif : Boolean"], ["+sAuthentifier() : Boolean", "+seDeconnecter() : void"]),
 "Role": (["-idRole : int", "-nom : String", "-description : String"], ["+attribuer(u : Utilisateur) : void"]),
 "Entreprise": (["-idEntreprise : int", "-nom : String", "-nif : String", "-stat : String", "-devise : String"], ["+choisirPlan(p : PlanComptable) : void"]),
 "PlanComptable": (["-idPlan : int", "-nom : String", "-pays : String"], ["+rechercherCompte(numero : String) : CompteComptable"]),
 "TauxChange": (["-idTaux : int", "-devise : String", "-taux : Decimal", "-dateEffet : Date"], ["+convertir(montant : Decimal) : Decimal"]),
 "Facture": (["-idFacture : int", "-numeroFacture : String", "-dateFacture : Date", "-typeFacture : String", "-devise : String",
              "-montantHT : Decimal", "-montantTVA : Decimal", "-montantTTC : Decimal", "-statut : String"],
             ["+importer(fichier : Document) : void", "+consulter() : Facture", "+supprimer() : void"]),
 "Document": (["-idDocument : int", "-nomFichier : String", "-typeFichier : String", "-taille : int", "-chemin : String"], ["+verifierFormat() : Boolean"]),
 "Fournisseur": (["-idFournisseur : int", "-raisonSociale : String", "-adresse : String", "-nif : String", "-stat : String"], []),
 "Client": (["-idClient : int", "-raisonSociale : String", "-adresse : String", "-nif : String"], []),
 "TraitementAutomatique": (["-etapeCourante : String", "-dateDebut : DateTime"], ["+lancer(f : Facture) : void", "+reprendre() : void"]),
 "Pretraitement": (["-resolution : int", "-netteteMesuree : Decimal"], ["+redresser() : void", "+debruiter() : void", "+binariser() : void"]),
 "TraitementOCR": (["-idOCR : int", "-moteur : String", "-texteExtrait : Text", "-scoreConfiance : Decimal", "-dureeMs : int"], ["+extraireTexte() : String", "+basculerMoteurSecours() : void"]),
 "InformationExtraite": (["-idInformation : int", "-typeInformation : String", "-valeur : String", "-scoreConfiance : Decimal"], []),
 "AnalyseNLP": (["-langue : String"], ["+detecterLangue() : String", "+extraireEntites() : List", "+identifierFournisseur() : String"]),
 "Analyse": (["-idAnalyse : int", "-natureOperation : String", "-scoreConfiance : Decimal"], ["+classerOperation() : String"]),
 "ModeleIA": (["-idModele : int", "-version : String", "-algorithme : String", "-f1Score : Decimal", "-actif : Boolean"],
              ["+predire(texte : String) : PredictionCompte", "+entrainer() : void", "+evaluer() : Decimal"]),
 "PredictionCompte": (["-idPrediction : int", "-numeroComptePropose : String", "-scoreConfiance : Decimal"], []),
 "MoteurComptable": ([], ["+appliquerRegles(a : Analyse) : void", "+genererEcriture() : EcritureComptable", "+verifierEquilibre() : Boolean"]),
 "RegleComptable": (["-idRegle : int", "-natureOperation : String", "-comptesCandidats : List", "-condition : String"], ["+verifier(compte : String) : Boolean"]),
 "EcritureComptable": (["-idEcriture : int", "-dateEcriture : Date", "-statut : String", "-totalDebit : Decimal", "-totalCredit : Decimal", "-scoreConfiance : Decimal"],
                       ["+ajouterLigne(l : LigneEcriture) : void", "+calculerScore() : Decimal", "+valider() : void"]),
 "LigneEcriture": (["-idLigne : int", "-libelle : String", "-montantDebit : Decimal", "-montantCredit : Decimal"], []),
 "CompteComptable": (["-numeroCompte : String", "-libelle : String", "-classe : int"], []),
 "Validation": (["-idValidation : int", "-decision : String", "-commentaire : String", "-dateValidation : DateTime"], ["+valider() : void", "+rejeter() : void"]),
 "Correction": (["-idCorrection : int", "-champ : String", "-ancienneValeur : String", "-nouvelleValeur : String", "-dateCorrection : DateTime"], ["+enregistrer() : void"]),
 "Historique": (["-idHistorique : int", "-action : String", "-description : String", "-dateAction : DateTime"], ["+enregistrer(action : String) : void"]),
}
S7 = [  # associations du sprint 7 (intégration)
 ("Utilisateur", "Role", "0..*", "1", "possède", "assoc"),
 ("Utilisateur", "Facture", "1", "0..*", "importe", "assoc"),
 ("Facture", "Document", "1", "1", "est stockée dans", "compo"),
 ("Facture", "Fournisseur", "0..*", "1", "émise par", "assoc"),
 ("Facture", "Client", "0..*", "0..1", "adressée à", "assoc"),
 ("TraitementAutomatique", "Facture", "0..*", "1", "traite", "assoc"),
 ("TraitementAutomatique", "Pretraitement", "1", "1", "étape 1", "compo"),
 ("TraitementAutomatique", "TraitementOCR", "1", "1", "étape 2", "compo"),
 ("TraitementOCR", "InformationExtraite", "1", "1..*", "produit", "compo"),
 ("TraitementAutomatique", "AnalyseNLP", "1", "1", "étape 3", "compo"),
 ("AnalyseNLP", "InformationExtraite", "", "1..*", "exploite", "dep"),
 ("AnalyseNLP", "Analyse", "1", "1", "produit", "assoc"),
 ("Analyse", "ModeleIA", "0..*", "1", "utilise", "assoc"),
 ("ModeleIA", "PredictionCompte", "1", "0..*", "produit", "assoc"),
 ("PredictionCompte", "CompteComptable", "0..*", "1", "désigne", "assoc"),
 ("MoteurComptable", "Analyse", "", "", "exploite", "dep"),
 ("MoteurComptable", "RegleComptable", "", "1..*", "applique", "dep"),
 ("RegleComptable", "CompteComptable", "0..*", "1..*", "autorise", "assoc"),
 ("MoteurComptable", "EcritureComptable", "", "", "génère", "dep"),
 ("Facture", "EcritureComptable", "1", "0..1", "donne lieu à", "assoc"),
 ("EcritureComptable", "LigneEcriture", "1", "2..*", "contient", "compo"),
 ("LigneEcriture", "CompteComptable", "0..*", "1", "imputée sur", "assoc"),
 ("EcritureComptable", "Validation", "1", "0..1", "fait l'objet de", "assoc"),
 ("EcritureComptable", "Correction", "1", "0..*", "peut subir", "assoc"),
 ("Facture", "Historique", "1", "0..*", "trace", "assoc"),
]


def design(name, classes, assocs, ga):
    b = '  node [shape=plain];\n'
    for n in classes:
        at, me = T[n]
        b += f'  "{n}" [label={cls(n, at, me)}];\n'
    for a, c, ma, mb, lab, k in assocs:
        b += assoc(a, c, ma, mb, lab, k)
    render(name, b, ga)


def sprint7():
    classes = sorted({x for r in S7 for x in r[:2]})
    design("classes_sprint7", classes, S7, 'rankdir=TB, nodesep=0.3, ranksep=0.5, splines=true')


def global_cls():
    G = list(S7) + [
        ("Entreprise", "Utilisateur", "1", "1..*", "emploie", "assoc"),
        ("Entreprise", "PlanComptable", "0..*", "1", "choisit", "assoc"),
        ("PlanComptable", "CompteComptable", "1", "1..*", "contient", "compo"),
        ("Entreprise", "Facture", "1", "0..*", "possède", "assoc"),
        ("Facture", "TauxChange", "0..*", "0..1", "convertie selon", "assoc"),
        ("Correction", "ModeleIA", "0..*", "0..1", "alimente", "assoc"),
    ]
    classes = sorted({x for r in G for x in r[:2]})
    design("classes_globale", classes, G, 'rankdir=TB, nodesep=0.3, ranksep=0.45, splines=true')


# =========================================================== 5. diagramme d'activité
def activity():
    b = '  node [shape=box, style="rounded,filled", fillcolor="#F4F6F9", color="#2F4B6B", fontsize=13];\n  edge [fontsize=11];\n'
    b += '  start [shape=circle, label="", width=0.25, style=filled, fillcolor=black];\n'
    b += '  stop [shape=doublecircle, label="", width=0.2, style=filled, fillcolor=black];\n'
    steps = [("a1", "Importer la facture\n(PDF ou image)"), ("a2", "Prétraiter la facture"), ("a3", "Extraire le texte\navec OCR"),
             ("a4", "Structurer les informations\nextraites"), ("a5", "Analyser le contenu\navec NLP"), ("a6", "Identifier la nature\nde l'opération"),
             ("a7", "Classer l'opération\navec le modèle ML"), ("a8", "Proposer les comptes\ncomptables"), ("a9", "Calculer le score\nde confiance")]
    for k, v in steps:
        b += f'  {k} [label="{v}"];\n'
    b += '  start -> a1;\n'
    for i in range(len(steps) - 1):
        cf = " [constraint=false]" if steps[i][0] in ("a3", "a6") else ""
        b += f"  {steps[i][0]} -> {steps[i+1][0]}{cf};\n"
    b += '  { rank=same; a1; a4; a7; } { rank=same; a2; a5; a8; } { rank=same; a3; a6; a9; }\n'
    b += '  a1 -> a4 -> a7 [style=invis]; a2 -> a5 -> a8 [style=invis]; a3 -> a6 -> a9 [style=invis];\n'
    # validation du score (nouvelle étape)
    b += '  v1 [shape=diamond, style=filled, fillcolor="#FFF4D6", label="Validation du score\\nscore ≥ 0,80 ?", fontsize=9];\n'
    b += '  v2 [label="Proposition\\nmarquée « fiable »", fillcolor="#E3F4E8"];\n'
    b += '  v3 [label="Proposition marquée\\n« à vérifier » (0,50 – 0,80)\\nou « vérification approfondie »\\n(< 0,50)", fillcolor="#FDE7E4"];\n'
    b += '  vn [shape=note, style=filled, fillcolor="#FFFDE8", fontsize=8, label="Méthode : validation par seuils\\nd\'un score agrégé (moyenne pondérée)\\n25 % OCR + 30 % extraction\\n+ 25 % classification + 20 % comptes"];\n'
    b += '  vm [shape=diamond, label="", width=0.3, height=0.3, style=filled, fillcolor=white];\n'
    b += '  a9 -> v1; v1 -> v2 [label="Oui"]; v1 -> v3 [label="Non"]; v2 -> vm; v3 -> vm;\n'
    b += '  vn -> v1 [style=dotted, arrowhead=none]; { rank=same; v1; vn; }\n'
    rest = [("b1", "Appliquer les règles\ncomptables"), ("b2", "Générer l'écriture\ncomptable"), ("b3", "Vérifier l'équilibre\nDébit = Crédit")]
    for k, v in rest:
        b += f'  {k} [label="{v}"];\n'
    b += '  vm -> b1; b1 -> b2; b2 -> b3; { rank=same; b1; b2; b3; }\n'
    b += '  d1 [shape=diamond, label="Écriture\\néquilibrée ?", fontsize=9, style=filled, fillcolor=white];\n  b3 -> d1;\n'
    b += '  c1 [label="Présenter la proposition\\nau comptable"]; e1 [label="Signaler une écriture\\ndéséquilibrée"]; e2 [label="Demander une correction"];\n'
    b += '  d1 -> c1 [label="Oui"]; d1 -> e1 [label="Non"]; e1 -> e2;\n'
    b += '  d2 [shape=diamond, label="Décision du\\ncomptable ?", fontsize=9, style=filled, fillcolor=white]; c1 -> d2;\n'
    b += '  f1 [label="Enregistrer l\'écriture\\nvalidée"]; f2 [label="Modifier l\'écriture"]; f3 [label="Enregistrer la correction"]; f4 [label="Rejeter la proposition"];\n'
    b += '  d2 -> f1 [label="Valider"]; d2 -> f2 [label="Modifier"]; d2 -> f4 [label="Rejeter"]; f2 -> f3;\n'
    b += '  h [label="Enregistrer l\'historique"]; f1 -> h; f3 -> h; f4 -> h; e2 -> h; h -> stop;\n'
    render("activite_ia", b, 'rankdir=TB, nodesep=0.35, ranksep=0.3')


def actor_png():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(0.9, 1.25), dpi=200)
    ax.add_patch(plt.Circle((0.5, 0.86), 0.1, fill=False, lw=1.6))
    for (x1, y1, x2, y2) in [(0.5, 0.76, 0.5, 0.42), (0.22, 0.64, 0.78, 0.64), (0.5, 0.42, 0.25, 0.12), (0.5, 0.42, 0.75, 0.12)]:
        ax.plot([x1, x2], [y1, y2], color="black", lw=1.6)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    fig.savefig(os.path.join(OUT, "actor.png"), transparent=True); plt.close(fig)


if __name__ == "__main__":
    actor_png(); use_case(); domain(); sprint7(); global_cls(); activity()
