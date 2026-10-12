"""Nettoyage et normalisation du texte extrait des documents.

Le but est d'obtenir un texte propre et homogène, quel que soit le format
d'origine, SANS modifier le sens : on corrige seulement les artefacts
techniques (espaces bizarres, césures de fin de ligne, en-têtes répétés…).
"""

import re
import unicodedata
from collections import Counter

# Ligatures typographiques fréquentes dans les PDF (« ﬁbres » -> « fibres »).
LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}

# Espaces spéciaux à remplacer par une espace normale
# (insécable, insécable fine utilisée avant « : » en français, etc.).
ESPACES_SPECIAUX = "       　"

# Caractères invisibles à supprimer (espace de largeur nulle, trait d'union conditionnel…).
INVISIBLES = "​‌‍⁠﻿­"

# Début de ligne qui indique un élément de liste : on ne le recolle pas à la ligne précédente.
DEBUT_LISTE = re.compile(r"^\s*([•●▪◦■□➢►\-–—*]|\d{1,2}[.)]\s|[a-z][.)]\s)")

# Fin de ligne qui termine une phrase ou un titre.
FIN_PHRASE = re.compile(r"[.!?:;»”]\s*$")


def normaliser_caracteres(texte: str) -> str:
    """Normalise l'Unicode (NFC), les ligatures, les espaces et les caractères invisibles."""
    texte = unicodedata.normalize("NFC", texte)
    for ligature, remplacement in LIGATURES.items():
        texte = texte.replace(ligature, remplacement)
    for espace in ESPACES_SPECIAUX:
        texte = texte.replace(espace, " ")
    for invisible in INVISIBLES:
        texte = texte.replace(invisible, "")
    # Fins de ligne Windows / Mac -> \n
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    # Caractères de contrôle (sauf \n et \t)
    texte = "".join(c for c in texte if c in "\n\t" or unicodedata.category(c)[0] != "C")
    return texte


def normaliser_espaces(texte: str) -> str:
    """Supprime les espaces en trop et limite les lignes vides consécutives à une seule."""
    texte = texte.replace("\t", " ")
    texte = re.sub(r" {2,}", " ", texte)
    texte = "\n".join(ligne.strip() for ligne in texte.split("\n"))
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    return texte.strip()


def recoller_cesures(texte: str) -> str:
    """Recolle les mots coupés en fin de ligne dans les PDF.

    « nutri-\\ntionnel » -> « nutritionnel » (la suite commence par une minuscule)
    « Nutri-\\nScore »   -> « Nutri-Score »  (majuscule : vrai trait d'union, on le garde)
    """
    texte = re.sub(r"(\w)-\n([a-zàâäéèêëîïôöùûüç])", r"\1\2", texte)
    texte = re.sub(r"(\w)-\n([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ0-9])", r"\1-\2", texte)
    return texte


def recoller_lignes(texte: str) -> str:
    """Reconstitue les paragraphes d'un PDF, où chaque ligne visuelle est coupée par \\n.

    Une ligne est recollée à la suivante, sauf :
    - si elle termine une phrase (., !, ?, :…) ;
    - si la ligne suivante commence une liste (puce, « 1. », « a) »…) ;
    - si l'une des deux est vide (séparation de paragraphe).
    """
    lignes = texte.split("\n")
    resultat: list[str] = []
    for ligne in lignes:
        if (
            resultat
            and resultat[-1]
            and ligne
            and not FIN_PHRASE.search(resultat[-1])
            and not DEBUT_LISTE.match(ligne)
        ):
            resultat[-1] = resultat[-1] + " " + ligne
        else:
            resultat.append(ligne)
    return "\n".join(resultat)


def _signature_ligne(ligne: str) -> str:
    """Forme simplifiée d'une ligne pour repérer les en-têtes/pieds de page répétés.

    Les chiffres ne sont neutralisés que si la ligne parle de « page »
    (« Guide 2019 - page 3 ») : sinon des lignes de contenu comme « Repère 1 »,
    « Repère 2 »… seraient prises à tort pour un en-tête répété.
    """
    ligne = re.sub(r"\s+", " ", ligne.strip().lower())
    if re.search(r"\bpage\b|\bp\.\s*\d", ligne):
        ligne = re.sub(r"\d+", "#", ligne)
    return ligne


def retirer_entetes_pieds(pages: list[str], seuil: float = 0.5) -> list[str]:
    """Supprime des pages d'un PDF :
    - les lignes répétées sur au moins `seuil` des pages (en-têtes, pieds de page) ;
    - les lignes qui ne contiennent qu'un numéro de page (« 12 », « Page 3 / 40 », « - 5 - »).

    On ne regarde que les 2 premières et 2 dernières lignes de chaque page,
    là où se trouvent les en-têtes et pieds de page.
    """
    numero_page = re.compile(r"^\s*(page\s*)?[-–]?\s*\d{1,4}\s*([/|]\s*\d{1,4})?\s*[-–]?\s*$", re.I)

    repetitions: Counter = Counter()
    if len(pages) >= 3:
        for page in pages:
            lignes = [l for l in page.split("\n") if l.strip()]
            bords = set(_signature_ligne(l) for l in lignes[:2] + lignes[-2:])
            repetitions.update(bords)
    repetees = {sig for sig, n in repetitions.items() if n >= seuil * len(pages) and len(sig) > 1}

    pages_nettoyees = []
    for page in pages:
        lignes = page.split("\n")
        non_vides = [i for i, l in enumerate(lignes) if l.strip()]
        bords = set(non_vides[:2] + non_vides[-2:])
        gardees = []
        for i, ligne in enumerate(lignes):
            if i in bords and (numero_page.match(ligne) or _signature_ligne(ligne) in repetees):
                continue
            gardees.append(ligne)
        pages_nettoyees.append("\n".join(gardees))
    return pages_nettoyees


def nettoyer(texte: str, mode_pdf: bool = False) -> str:
    """Nettoyage complet d'un bloc de texte.

    `mode_pdf=True` active en plus le recollage des césures et des lignes,
    nécessaire uniquement pour le texte issu des PDF.
    """
    texte = normaliser_caracteres(texte)
    texte = normaliser_espaces(texte)
    if mode_pdf:
        texte = recoller_cesures(texte)
        texte = recoller_lignes(texte)
        texte = normaliser_espaces(texte)
    return texte
